export type RunPhase = 'idle' | 'submitting' | 'queued' | 'running' | 'loading_result' | 'completed' | 'failed'

export interface Campaign {
  campaign_name: string
  filter_arpu_segment: string | null
  filter_data_segment: string | null
  filter_call_segment: string | null
  filter_current_tariff: string | null
  target_tariff: string
  channel: string
}

export interface RunResult {
  environment: string
  campaign_count: number
  campaigns: Campaign[]
  metrics?: RunMetrics
  pilots?: Pilot[]
}

export interface RunMetrics {
  net_arpu_gain: number
  total_cost: number
  total_budget: number
  remaining_budget: number
}

export interface Pilot {
  pilot: string
  target_tariff: string
  channel: string
  n_customers: number
  cost: number
  observed_lift_ratio: number
  observed_lift_total: number
  remaining_budget: number
  remaining_contacts: number
}

export const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number, options?: ErrorOptions) {
    super(message, options)
    this.name = 'ApiError'
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function request(path: string, signal: AbortSignal, method = 'GET'): Promise<Response> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      signal: AbortSignal.any([signal, AbortSignal.timeout(20_000)]),
      cache: 'no-store',
    })
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null)
      const detail = isRecord(body) && typeof body.detail === 'string' ? body.detail : null
      throw new ApiError(response.status === 404
        ? 'Запуск больше не найден. Возможно, сервер перезапустился. Запустите агента заново.'
        : detail || `Ошибка API (${response.status}). Проверьте, что бэкенд запущен.`, response.status)
    }
    return response
  } catch (error) {
    if (signal.aborted || error instanceof ApiError) throw error
    if (error instanceof Error && error.name === 'TimeoutError') {
      throw new ApiError('Сервер не ответил за 20 секунд. Проверьте подключение и повторите запуск.', 0, { cause: error })
    }
    throw new ApiError('Нет связи с API. Проверьте, что бэкенд запущен, и повторите попытку.', 0, { cause: error })
  }
}

async function json(path: string, signal: AbortSignal, method?: string): Promise<unknown> {
  const response = await request(path, signal, method)
  try {
    return await response.json()
  } catch {
    throw new Error('API вернул некорректный ответ вместо JSON.')
  }
}

export async function checkHealth(signal: AbortSignal): Promise<void> {
  const body = await json('/health', signal)
  if (!isRecord(body) || body.status !== 'ok') throw new Error('API недоступен')
}

export function parseResult(body: unknown): RunResult {
  const required = ['campaign_name', 'target_tariff', 'channel']
  const filters = ['filter_arpu_segment', 'filter_data_segment', 'filter_call_segment', 'filter_current_tariff']
  if (!isRecord(body) || typeof body.environment !== 'string' || !Array.isArray(body.campaigns)
    || body.campaign_count !== body.campaigns.length
    || !body.campaigns.every((row: unknown) => isRecord(row)
      && required.every((key) => typeof row[key] === 'string' && row[key] !== '')
      && filters.every((key) => row[key] === null || typeof row[key] === 'string'))) {
    throw new Error('Формат результата API не соответствует списку кампаний.')
  }
  if (body.metrics !== undefined) {
    const metrics = body.metrics
    if (!isRecord(metrics) || !['net_arpu_gain', 'total_cost', 'total_budget', 'remaining_budget']
      .every((key) => typeof metrics[key] === 'number' && Number.isFinite(metrics[key]))) {
      throw new Error('API вернул некорректные финансовые показатели.')
    }
  }
  if (body.pilots !== undefined && (!Array.isArray(body.pilots) || !body.pilots.every((pilot: unknown) =>
    isRecord(pilot)
    && ['pilot', 'target_tariff', 'channel'].every((key) => typeof pilot[key] === 'string' && pilot[key] !== '')
    && ['n_customers', 'cost', 'observed_lift_ratio', 'observed_lift_total', 'remaining_budget', 'remaining_contacts']
      .every((key) => typeof pilot[key] === 'number' && Number.isFinite(pilot[key]))
    && Number.isInteger(pilot.n_customers) && (pilot.n_customers as number) >= 0))) {
    throw new Error('API вернул некорректную историю пилотов.')
  }
  return body as unknown as RunResult
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted()
    const abort = () => {
      clearTimeout(timer)
      reject(signal.reason)
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      resolve()
    }, ms)
    signal.addEventListener('abort', abort, { once: true })
  })
}

export async function runAgent(
  onProgress: (phase: RunPhase, runId: string) => void,
  signal: AbortSignal,
): Promise<{ runId: string; result: RunResult }> {
  const created = await json('/runs', signal, 'POST')
  if (!isRecord(created) || typeof created.run_id !== 'string' || !created.run_id) {
    throw new Error('API не вернул идентификатор запуска.')
  }
  const runId = created.run_id
  const path = `/runs/${encodeURIComponent(runId)}`
  onProgress('queued', runId)
  while (true) {
    signal.throwIfAborted()
    const state = await json(path, signal)
    if (!isRecord(state) || state.run_id !== runId) throw new Error('Некорректный статус запуска от API.')
    if (state.status === 'failed') {
      throw new Error(typeof state.error === 'string' && state.error ? state.error : 'Агент завершился с ошибкой.')
    }
    if (state.status === 'completed') {
      onProgress('loading_result', runId)
      const result = parseResult(await json(`${path}/result`, signal))
      return { runId, result }
    }
    if (state.status !== 'queued' && state.status !== 'running') throw new Error('Неизвестный статус запуска от API.')
    onProgress(state.status, runId)
    await delay(1000, signal)
  }
}

export async function getSubmission(runId: string, signal: AbortSignal): Promise<Blob> {
  const response = await request(`/runs/${encodeURIComponent(runId)}/submission`, signal)
  if (!response.headers.get('content-type')?.includes('text/csv')) {
    throw new Error('API вернул некорректный файл вместо CSV.')
  }
  return response.blob()
}
