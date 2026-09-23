import { useEffect, useMemo, useState } from 'react'
import {
  BarChart3, Check, ChevronDown, CircleDollarSign, Download, FlaskConical,
  Gauge, LayoutDashboard, Megaphone, MoreHorizontal, Play, Radio, Sparkles,
  Target, Users, WalletCards,
} from 'lucide-react'
import {
  Bar, CartesianGrid, Cell, ComposedChart, ErrorBar, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import beelineLogo from './assets/beeline-logo.png'
import './App.css'

type RunState = 'idle' | 'running' | 'done'

const pilotData = [
  { segment: 'HIGH · HEAVY', value: 12.4, error: 3.2 },
  { segment: 'MID · HEAVY', value: 7.1, error: 2.2 },
  { segment: 'HIGH · MEDIUM', value: 3.9, error: 1.7 },
  { segment: 'LOW · LITE', value: -2.3, error: 1.6 },
]

const campaigns = [
  { segment: 'HIGH · HEAVY', transition: 'tariff_8 → tariff_10', channel: 'SMS', channelClass: 'sms', reach: '2 400', cost: '9 600', confidence: 'Высокая', confidenceClass: 'high' },
  { segment: 'MID · HEAVY', transition: 'tariff_13 → tariff_14', channel: 'Push', channelClass: 'push', reach: '3 100', cost: '0', confidence: 'Высокая', confidenceClass: 'high' },
  { segment: 'HIGH · MEDIUM', transition: 'tariff_4 → tariff_18', channel: 'Реклама', channelClass: 'ads', reach: '900', cost: '19 800', confidence: 'Средняя', confidenceClass: 'medium' },
]

const steps = [
  ['Аудитория изучена', '100% сегментов обработано'],
  ['Гипотезы сформированы', 'Сгенерировано 28 гипотез'],
  ['12 пилотов завершено', 'Собраны и проанализированы результаты'],
  ['План кампаний сформирован', 'Каналы, охват и ROI рассчитаны'],
]

function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function App() {
  const [runState, setRunState] = useState<RunState>('idle')
  const [activeStep, setActiveStep] = useState(3)

  useEffect(() => {
    if (runState !== 'running') return
    const timers = [1, 2, 3].map((step) => window.setTimeout(() => setActiveStep(step), step * 850))
    const finishTimer = window.setTimeout(() => setRunState('done'), 3400)
    return () => {
      timers.forEach(window.clearTimeout)
      window.clearTimeout(finishTimer)
    }
  }, [runState])

  function startAgent() {
    setActiveStep(0)
    setRunState('running')
  }

  const buttonLabel = useMemo(() => {
    if (runState === 'running') return 'Агент работает'
    if (runState === 'done') return 'Запустить снова'
    return 'Запустить агента'
  }, [runState])

  function downloadCsv() {
    const header = 'segment,current_tariff,target_tariff,channel,reach,cost,confidence\n'
    const rows = [
      'HIGH · HEAVY,tariff_8,tariff_10,sms,2400,9600,high',
      'MID · HEAVY,tariff_13,tariff_14,push,3100,0,high',
      'HIGH · MEDIUM,tariff_4,tariff_18,digital_ads,900,19800,medium',
    ].join('\n')
    const url = URL.createObjectURL(new Blob([header + rows], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'submission-preview.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => scrollToSection('overview')} aria-label="На главную">
          <img className="brand-mark" src={beelineLogo} alt="" />
          <span><strong>beeline</strong><small>Campaign AI</small></span>
        </button>
        <nav aria-label="Навигация по дашборду">
          <button className="nav-item active" onClick={() => scrollToSection('overview')}><LayoutDashboard size={21} /><span>Обзор</span></button>
          <button className="nav-item" onClick={() => scrollToSection('audience')}><Users size={21} /><span>Аудитория</span></button>
          <button className="nav-item" onClick={() => scrollToSection('pilots')}><FlaskConical size={21} /><span>Пилоты</span></button>
          <button className="nav-item" onClick={() => scrollToSection('campaigns')}><Megaphone size={21} /><span>Кампании</span></button>
          <button className="nav-item" onClick={() => scrollToSection('campaigns')}><BarChart3 size={21} /><span>Отчёты</span></button>
        </nav>
        <div className="agent-ready"><span className="status-dot" /><span><strong>Агент готов</strong><small>Работает в фоновом режиме</small></span></div>
      </aside>

      <main>
        <header className="topbar">
          <div className="breadcrumbs"><span>Рабочее пространство</span><b>/</b> Обзор</div>
          <div className="topbar-right">
            <span className="demo-pill"><CircleDollarSign size={15} /> Демо · синтетические данные</span>
            <span className="divider" /><span className="avatar">АС</span>
            <span className="profile"><strong>Асет</strong><small>Команда HackAlem</small></span><ChevronDown size={17} />
          </div>
        </header>

        <div className="dashboard" id="overview">
          <section className="page-heading">
            <div><h1>Умные кампании. Измеримый рост.</h1><p>От исследования аудитории до готового плана кампаний</p></div>
            <div className="heading-actions">
              <button className="primary-button" onClick={startAgent} disabled={runState === 'running'}>
                {runState === 'running' ? <Sparkles className="spin" size={19} /> : <Play size={19} fill="currentColor" />}{buttonLabel}
              </button>
              <button className="secondary-button" onClick={downloadCsv} disabled={runState !== 'done'} title={runState === 'done' ? 'Скачать CSV' : 'Сначала запустите агента'}><Download size={19} /> Экспорт CSV</button>
            </div>
          </section>

          <section className="metrics-grid" id="audience">
            <article className="metric-card"><span className="metric-icon"><Gauge size={24} /></span><div><small>Чистый прирост ARPU</small><strong>+428 600 у.е.</strong><p>После затрат на коммуникации</p></div></article>
            <article className="metric-card"><span className="metric-icon"><WalletCards size={24} /></span><div><small>Бюджет</small><strong>29 400 / 100 000</strong><p>Использовано, у.е.</p></div></article>
            <article className="metric-card"><span className="metric-icon"><FlaskConical size={24} /></span><div><small>Пилоты</small><strong>12 / 20</strong><p>Проведено исследований</p></div></article>
            <article className="metric-card"><span className="metric-icon"><Target size={24} /></span><div><small>Охват</small><strong>8 420 / 15 000</strong><p>Контакты с учётом пилотов</p></div></article>
          </section>

          <section className="insights-grid" id="pilots">
            <article className="panel pilot-panel">
              <div className="panel-heading"><h2>Результаты пилотов</h2><span>Оценка эффекта · демо</span></div>
              <div className="chart-wrap" aria-label="График наблюдаемого прироста ARPU">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={pilotData} layout="vertical" margin={{ top: 8, right: 45, bottom: 22, left: 8 }}>
                    <CartesianGrid stroke="#e8e9ed" horizontal={false} />
                    <XAxis type="number" domain={[-10, 20]} ticks={[-10, -5, 0, 5, 10, 15, 20]} tickLine={false} axisLine={{ stroke: '#ccd0d7' }} label={{ value: 'Наблюдаемый прирост ARPU, %', position: 'bottom', offset: 7 }} />
                    <YAxis dataKey="segment" type="category" width={132} tickLine={false} axisLine={false} />
                    <Tooltip cursor={{ fill: '#f7f7f8' }} formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Прирост ARPU']} />
                    <ReferenceLine x={0} stroke="#747b87" />
                    <Bar dataKey="value" barSize={28} radius={[0, 2, 2, 0]}>
                      {pilotData.map((entry) => <Cell key={entry.segment} fill={entry.value >= 0 ? '#22a559' : '#f06464'} />)}
                      <ErrorBar dataKey="error" width={7} strokeWidth={1.5} stroke="#68707d" direction="x" />
                    </Bar>
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="panel progress-panel">
              <h2>Ход работы агента</h2>
              <div className="timeline">
                {steps.map(([title, detail], index) => {
                  const completed = index < activeStep || runState === 'done'
                  const current = index === activeStep && runState !== 'done'
                  return <div className={`timeline-item ${completed ? 'completed' : ''} ${current ? 'current' : ''}`} key={title}>
                    <span className="timeline-icon">{completed ? <Check size={15} /> : current ? <Radio size={14} /> : index + 1}</span>
                    <div><strong>{title}</strong><small>{detail}</small></div><time>{['10:12', '10:14', '10:28', '10:31'][index]}</time>
                  </div>
                })}
              </div>
              <div className="hint"><Sparkles size={18} /> Проверяем эффект и надёжность каждого сегмента.</div>
            </article>
          </section>

          <section className="panel campaigns-panel" id="campaigns">
            <div className="panel-heading campaign-title"><h2>Рекомендуемые кампании</h2><span>3 кампании</span></div>
            <div className="table-scroll"><table>
              <thead><tr><th>Сегмент</th><th>Переход тарифа</th><th>Канал</th><th>Охват</th><th>Затраты, у.е.</th><th>Надёжность</th><th><span className="sr-only">Действия</span></th></tr></thead>
              <tbody>{campaigns.map((campaign) => <tr key={campaign.transition}>
                <td><strong>{campaign.segment}</strong></td><td>{campaign.transition}</td>
                <td><span className={`channel ${campaign.channelClass}`}><Megaphone size={15} />{campaign.channel}</span></td>
                <td>{campaign.reach}</td><td>{campaign.cost}</td>
                <td><span className={`confidence ${campaign.confidenceClass}`}><i />{campaign.confidence}</span></td>
                <td><button className="icon-button" aria-label={`Действия для ${campaign.segment}`}><MoreHorizontal size={20} /></button></td>
              </tr>)}</tbody>
            </table></div>
          </section>
        </div>
      </main>
    </div>
  )
}

export default App
