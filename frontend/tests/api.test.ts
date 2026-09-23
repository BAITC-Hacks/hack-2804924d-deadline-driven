import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { ApiError, getSubmission, parseResult, runAgent } from '../src/api.ts'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })
const result = {
  environment: 'mock', campaign_count: 1,
  campaigns: [{ campaign_name: 'test', filter_arpu_segment: 'HIGH',
    filter_data_segment: null, filter_call_segment: null, filter_current_tariff: 'tariff_1',
    target_tariff: 'tariff_3', channel: 'sms' }],
}
const metrics = { net_arpu_gain: -12, total_cost: 40, total_budget: 100, remaining_budget: 60 }
const pilots = [{ pilot: 'pilot_1', target_tariff: 'tariff_3', channel: 'sms',
  n_customers: 10, cost: 40, observed_lift_ratio: -0.12, observed_lift_total: -120,
  remaining_budget: 60, remaining_contacts: 14990 }]
function sequence(responses: Response[]) {
  const calls: { url: string; method: string; time: number }[] = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), method: options?.method ?? 'GET', time: Date.now() })
    const response = responses.shift()
    assert.ok(response, 'Unexpected extra request')
    return response
  }
  return calls
}

test('polls sequentially and fetches the result only after completed', async () => {
  const calls = sequence([
    Response.json({ run_id: 'run1' }, { status: 202 }),
    Response.json({ run_id: 'run1', status: 'queued', error: null }),
    Response.json({ run_id: 'run1', status: 'running', error: null }),
    Response.json({ run_id: 'run1', status: 'completed', error: null }),
    Response.json(result),
  ])
  const phases: string[] = []
  const completed = await runAgent((phase) => phases.push(phase), new AbortController().signal)
  assert.deepEqual(completed, { runId: 'run1', result })
  assert.deepEqual(phases, ['queued', 'queued', 'running', 'loading_result'])
  assert.deepEqual(calls.map(({ url, method }) => `${method} ${url}`), [
    'POST /api/runs', 'GET /api/runs/run1', 'GET /api/runs/run1',
    'GET /api/runs/run1', 'GET /api/runs/run1/result',
  ])
  assert.ok(calls[2].time - calls[1].time >= 950)
  assert.ok(calls[3].time - calls[2].time >= 950)
})

test('failed stops polling and preserves the agent error', async () => {
  const calls = sequence([
    Response.json({ run_id: 'run1' }),
    Response.json({ run_id: 'run1', status: 'failed', error: 'Agent test failure' }),
  ])
  await assert.rejects(runAgent(() => {}, new AbortController().signal), /Agent test failure/)
  assert.equal(calls.length, 2)
})

test('server restart (404) stops polling with an actionable error', async () => {
  const calls = sequence([
    Response.json({ run_id: 'run1' }),
    Response.json({ detail: 'Not found' }, { status: 404 }),
  ])
  await assert.rejects(runAgent(() => {}, new AbortController().signal), (error: unknown) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 404)
    assert.match(error.message, /Запустите агента заново/)
    return true
  })
  assert.equal(calls.length, 2)
})

test('cancellation stops further status requests', async () => {
  const calls = sequence([Response.json({ run_id: 'run1' })])
  const controller = new AbortController()
  await assert.rejects(runAgent(() => controller.abort(), controller.signal), { name: 'AbortError' })
  assert.equal(calls.length, 1)
})

test('network failure is reported without silently retrying POST', async () => {
  let count = 0
  globalThis.fetch = async () => { count++; throw new TypeError('Network failed') }
  await assert.rejects(runAgent(() => {}, new AbortController().signal), /Нет связи с API/)
  assert.equal(count, 1)
})

test('unknown status is not polled forever', async () => {
  const calls = sequence([Response.json({ run_id: 'run1' }), Response.json({ run_id: 'run1', status: 'unknown' })])
  await assert.rejects(runAgent(() => {}, new AbortController().signal), /Неизвестный статус/)
  assert.equal(calls.length, 2)
})

test('result schema accepts empty plans but rejects inconsistent counts and missing filters', () => {
  assert.deepEqual(parseResult({ environment: 'mock', campaign_count: 0, campaigns: [] }).campaigns, [])
  assert.throws(() => parseResult({ ...result, campaign_count: 20 }))
  assert.throws(() => parseResult({ ...result, campaigns: [{ campaign_name: 'bad' }] }))
})

test('CSV is downloaded from the same run with no extra calculation', async () => {
  const csv = 'campaign_name,channel\r\ntest,sms\r\n'
  const calls = sequence([new Response(csv, { headers: { 'Content-Type': 'text/csv; charset=utf-8' } })])
  assert.equal(await (await getSubmission('run1', new AbortController().signal)).text(), csv)
  assert.deepEqual(calls.map(({ url }) => url), ['/api/runs/run1/submission'])
})

test('download detects a stale run and rejects HTML instead of CSV', async () => {
  sequence([Response.json({ detail: 'Not found' }, { status: 404 })])
  await assert.rejects(getSubmission('run1', new AbortController().signal), { status: 404 })
  sequence([new Response('<html></html>', { headers: { 'Content-Type': 'text/html' } })])
  await assert.rejects(getSubmission('run1', new AbortController().signal), /вместо CSV/)
})

test('metrics and pilots are preserved from the result without synthesizing values', () => {
  const response = { ...result, metrics, pilots }
  assert.deepEqual(parseResult(response), response)
  assert.equal(parseResult(result).metrics, undefined)
  assert.equal(parseResult(result).pilots, undefined)
  assert.deepEqual(parseResult({ ...result, pilots: [] }).pilots, [])
})

test('zero values and negative financial and pilot effects remain valid', () => {
  assert.equal(parseResult({ ...result, metrics, pilots }).metrics?.net_arpu_gain, -12)
  const zeros = { net_arpu_gain: 0, total_cost: 0, total_budget: 100, remaining_budget: 100 }
  assert.deepEqual(parseResult({ ...result, metrics: zeros }).metrics, zeros)
})

test('invalid financial and pilot fields are rejected instead of shown as numbers', () => {
  assert.throws(() => parseResult({ ...result, metrics: { ...metrics, total_cost: '40' } }))
  assert.throws(() => parseResult({ ...result, metrics: { ...metrics, net_arpu_gain: NaN } }))
  assert.throws(() => parseResult({ ...result, metrics: { ...metrics, remaining_budget: Infinity } }))
  assert.throws(() => parseResult({ ...result, pilots: [{ ...pilots[0], observed_lift_ratio: null }] }))
  assert.throws(() => parseResult({ ...result, pilots: [{ ...pilots[0], n_customers: -1 }] }))
})
