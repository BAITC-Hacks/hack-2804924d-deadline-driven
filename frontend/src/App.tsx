import { useEffect, useRef, useState } from 'react'
import {
  Activity, AlertCircle, ArrowRight, CheckCircle2, Database, Download,
  ChevronDown, FlaskConical, LayoutDashboard, LoaderCircle, Megaphone, MessageSquare,
  Phone, Play, Smartphone, TrendingUp, Wallet, Coins,
} from 'lucide-react'
import { ApiError, checkHealth, getSubmission, runAgent } from './api'
import type { RunPhase, RunResult } from './api'
import beelineLogo from './assets/beeline-logo.png'
import './App.css'

const phaseLabels: Record<RunPhase, string> = {
  idle: 'Ожидает запуска', submitting: 'Создаём запуск', queued: 'В очереди',
  running: 'Агент работает', loading_result: 'Получаем результат',
  completed: 'Расчёт завершён', failed: 'Запуск не завершён',
}
const channels: Record<string, { label: string; icon: typeof Megaphone }> = {
  sms: { label: 'SMS', icon: MessageSquare }, push: { label: 'Push', icon: Smartphone },
  digital_ads: { label: 'Реклама', icon: Megaphone }, call: { label: 'Звонок', icon: Phone },
}

const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
const percentFormat = new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 1, signDisplay: 'exceptZero' })

function Channel({ value }: { value: string }) {
  const channel = channels[value]
  const Icon = channel?.icon ?? Megaphone
  return <span className={`channel ${value}`}><Icon size={15} />{channel?.label ?? value}</span>
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Не удалось выполнить запрос.'
}

function App() {
  const [phase, setPhase] = useState<RunPhase>('idle')
  const [runId, setRunId] = useState<string | null>(null)
  const [result, setResult] = useState<RunResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [connection, setConnection] = useState<'checking' | 'online' | 'offline'>('checking')
  const activeRequest = useRef<AbortController | null>(null)
  const downloadRequest = useRef<AbortController | null>(null)
  const busy = !['idle', 'completed', 'failed'].includes(phase)

  useEffect(() => {
    const controller = new AbortController()
    checkHealth(controller.signal).then(() => {
      if (!controller.signal.aborted) setConnection('online')
    }).catch(() => {
      if (!controller.signal.aborted) setConnection('offline')
    })
    return () => {
      controller.abort()
      activeRequest.current?.abort()
      downloadRequest.current?.abort()
    }
  }, [])

  async function startAgent() {
    if (activeRequest.current || downloadRequest.current) return
    const controller = new AbortController()
    activeRequest.current = controller
    setPhase('submitting')
    setResult(null)
    setRunId(null)
    setError(null)
    setDownloadError(null)
    try {
      const completed = await runAgent((nextPhase, id) => {
        if (controller.signal.aborted) return
        setPhase(nextPhase)
        setRunId(id)
        setConnection('online')
      }, controller.signal)
      if (controller.signal.aborted) return
      setResult(completed.result)
      setPhase('completed')
    } catch (cause) {
      if (controller.signal.aborted) return
      setError(errorMessage(cause))
      setPhase('failed')
      if (cause instanceof ApiError && (cause.status === 0 || cause.status >= 500)) setConnection('offline')
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null
    }
  }

  async function downloadCsv() {
    if (!runId || !result || activeRequest.current || downloadRequest.current) return
    const controller = new AbortController()
    downloadRequest.current = controller
    setDownloading(true)
    setDownloadError(null)
    try {
      const blob = await getSubmission(runId, controller.signal)
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'submission.csv'
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) {
      if (controller.signal.aborted) return
      if (cause instanceof ApiError && (cause.status === 0 || cause.status >= 500)) setConnection('offline')
      if (cause instanceof ApiError && cause.status === 404) {
        setResult(null)
        setPhase('failed')
        setError(errorMessage(cause))
      } else setDownloadError(errorMessage(cause))
    } finally {
      if (downloadRequest.current === controller) downloadRequest.current = null
      if (!controller.signal.aborted) setDownloading(false)
    }
  }

  const metrics = [
    { label: 'Кампании', value: result?.campaign_count, icon: Megaphone, unit: '' },
    { label: 'Чистый прирост', value: result?.metrics?.net_arpu_gain, icon: TrendingUp, unit: 'у.е.' },
    { label: 'Затраты', value: result?.metrics?.total_cost, icon: Coins, unit: 'у.е.' },
    { label: 'Остаток бюджета', value: result?.metrics?.remaining_budget, icon: Wallet, unit: 'у.е.' },
  ]
  const StatusIcon = busy ? LoaderCircle : phase === 'completed' ? CheckCircle2 : phase === 'failed' ? AlertCircle : Activity
  const connectionLabel = connection === 'online' ? 'Сервис доступен' : connection === 'offline' ? 'Сервис недоступен' : 'Проверяем сервис'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="Beeline Campaign AI, обзор">
          <img className="brand-mark" src={beelineLogo} alt="" />
          <span><strong>beeline</strong><small>Campaign AI</small></span>
        </a>
        <nav aria-label="Навигация">
          <a className="nav-item active" href="#overview" title="Обзор" aria-label="Обзор"><LayoutDashboard size={21} /><span>Обзор</span></a>
          <a className="nav-item" href="#campaigns" title="Кампании" aria-label="Кампании"><Megaphone size={21} /><span>Кампании</span></a>
          <a className="nav-item" href="#pilots" title="Пилоты" aria-label="Пилоты"><FlaskConical size={21} /><span>Пилоты</span></a>
        </nav>
        <div className={`connection ${connection}`} role="status" title={connectionLabel} aria-label={connectionLabel}>
          <span className="status-dot" />
          <span>{connectionLabel}</span>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <span>Рабочее пространство <b>/</b> Обзор</span>
          <span className="team-label">HackAlem 2026</span>
        </header>

        <div className="dashboard" id="overview">
          <section className="page-heading">
            <div><p className="eyebrow">BEELINE CAMPAIGN AI</p><h1>Тарифные кампании</h1></div>
            <div className="heading-actions">
              <button className="primary-button" onClick={startAgent} disabled={busy || downloading}>
                {busy ? <LoaderCircle className="spin" size={18} /> : <Play size={18} />}
                {busy ? 'Агент работает' : phase === 'idle' ? 'Запустить агента' : 'Запустить снова'}
              </button>
              <button className="secondary-button" onClick={downloadCsv} disabled={!result || busy || downloading}>
                {downloading ? <LoaderCircle className="spin" size={18} /> : <Download size={18} />}
                {downloading ? 'Скачивание' : 'Экспорт CSV'}
              </button>
            </div>
          </section>

          <section className={`run-strip ${phase}`} aria-label="Текущий запуск" aria-busy={busy}>
            <StatusIcon className={busy ? 'spin' : ''} size={25} />
            <div className="run-detail"><strong role="status">{phaseLabels[phase]}</strong>
              {!runId && <span>Нет активного запуска</span>}
            </div>
            <span className="environment"><Database size={15} />{result && result.environment !== 'mock' ? result.environment : 'Демонстрационные данные'}</span>
          </section>
          {runId && <details className="run-details" key={runId}>
            <summary><ChevronDown size={16} />Детали запуска</summary>
            <dl><div><dt>Идентификатор</dt><dd><code>{runId}</code></dd></div>
              <div><dt>Источник</dt><dd><code>/runs/{runId}/result</code></dd></div>
            </dl>
          </details>}

          {error && <div className="error-banner" role="alert"><AlertCircle size={20} /><p>{error}</p></div>}
          {downloadError && <div className="error-banner" role="alert"><AlertCircle size={20} /><p>{downloadError}</p></div>}

          <section className="metrics-grid" aria-label="Итоги расчёта">
            {metrics.map(({ label, value, icon: Icon, unit }) => <article className="metric" key={label}>
              <div className="metric-label"><Icon size={20} /><span>{label}</span></div>
              <div className="metric-value"><strong>{value === undefined ? '—' : numberFormat.format(value)}</strong>{value !== undefined && unit && <small>{unit}</small>}</div>
            </article>)}
          </section>
          {result && <p className="metrics-note">{result.metrics ? 'Показатели учитывают пилоты и итоговые кампании.' : 'Финансовые показатели недоступны в этом запуске.'}</p>}

          <section className="campaigns-section" id="campaigns" aria-busy={busy}>
            <div className="section-heading"><h2>План кампаний</h2><span>{result ? `Кампаний: ${result.campaign_count}` : 'Результатов пока нет'}</span></div>
            {result && result.campaigns.length > 0 ? <div className="table-scroll" role="region" aria-label="Кампании агента" tabIndex={0}><table>
              <caption className="sr-only">Итоговые кампании завершённого запуска</caption>
              <thead><tr><th>Кампания</th><th>ARPU</th><th>Интернет</th><th>Звонки</th><th>Переход тарифа</th><th>Канал</th></tr></thead>
              <tbody>{result.campaigns.map((campaign, index) => <tr key={`${campaign.campaign_name}-${index}`}>
                  <td className="campaign-name">{campaign.campaign_name}</td>
                  <td>{campaign.filter_arpu_segment || 'Любой'}</td>
                  <td>{campaign.filter_data_segment || 'Любой'}</td>
                  <td>{campaign.filter_call_segment || 'Любой'}</td>
                  <td><span className="tariff-transition"><span>{campaign.filter_current_tariff || 'Все тарифы'}</span><ArrowRight size={15} aria-label="на" /><strong>{campaign.target_tariff}</strong></span></td>
                  <td><Channel value={campaign.channel} /></td>
                </tr>
              )}</tbody>
            </table></div> : <div className="empty-state">
              {busy ? <LoaderCircle className="spin" size={32} /> : <Megaphone size={32} />}
              <h3>{busy ? 'Выполняется расчёт' : phase === 'failed' ? 'Результат недоступен' : result ? 'Кампаний нет' : 'Кампании ещё не рассчитаны'}</h3>
              <p>{busy ? phaseLabels[phase] : phase === 'failed' ? 'Запуск завершился без доступного результата.' : result ? 'Агент вернул пустой план.' : 'Ожидаем первый запуск агента.'}</p>
            </div>}
          </section>
          <section className="pilots-section" id="pilots" aria-busy={busy}>
            <div className="section-heading"><h2>Результаты пилотов</h2><span>{result?.pilots ? `Пилотов: ${result.pilots.length}` : 'Результатов пока нет'}</span></div>
            {result?.pilots && result.pilots.length > 0 ? <div className="table-scroll" role="region" aria-label="Пилоты агента" tabIndex={0}><table>
              <caption className="sr-only">Наблюдаемые результаты пилотов этого запуска</caption>
              <thead><tr><th>Пилот</th><th>Целевой тариф</th><th>Канал</th><th className="numeric">Абоненты</th><th className="numeric">Наблюдаемый прирост, %</th><th className="numeric">Затраты, у.е.</th></tr></thead>
              <tbody>{result.pilots.map((pilot) => <tr key={pilot.pilot}>
                <td className="campaign-name">{pilot.pilot}</td><td>{pilot.target_tariff}</td>
                <td><Channel value={pilot.channel} /></td>
                <td className="numeric">{numberFormat.format(pilot.n_customers)}</td>
                <td className={`numeric ${pilot.observed_lift_ratio < 0 ? 'negative-value' : pilot.observed_lift_ratio > 0 ? 'positive-value' : ''}`}>{percentFormat.format(pilot.observed_lift_ratio)}</td>
                <td className="numeric">{numberFormat.format(pilot.cost)}</td>
              </tr>)}</tbody>
            </table></div> : <div className="empty-state pilots-empty">
              <FlaskConical size={28} />
              <h3>{busy ? 'Пилоты выполняются' : result?.pilots ? 'Пилоты не проводились' : result ? 'История пилотов недоступна' : 'Пилотов пока нет'}</h3>
            </div>}
          </section>
          <footer className="dashboard-footer"><span>Beeline · HackAlem</span><span>Локальная среда оценки</span></footer>
        </div>
      </main>
    </div>
  )
}

export default App
