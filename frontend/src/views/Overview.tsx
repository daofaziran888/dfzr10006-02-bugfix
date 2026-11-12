import { useEffect, useState } from 'react'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

const fallbackCards = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
const fallbackModules = [{"name": "服务注册发现", "created": 0, "pending": 0, "abnormal": 0}, {"name": "查询路由分发", "created": 0, "pending": 0, "abnormal": 0}, {"name": "结果缓存加速", "created": 0, "pending": 0, "abnormal": 0}, {"name": "调用限流降级", "created": 0, "pending": 0, "abnormal": 0}, {"name": "服务编排组合", "created": 0, "pending": 0, "abnormal": 0}, {"name": "调用链追踪", "created": 0, "pending": 0, "abnormal": 0}, {"name": "服务健康诊断", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据接口契约", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据订阅推送", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据加工转换", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据模拟服务", "created": 0, "pending": 0, "abnormal": 0}, {"name": "接入网关管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "服务指标采集", "created": 0, "pending": 0, "abnormal": 0}, {"name": "调用来源管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "负载均衡策略", "created": 0, "pending": 0, "abnormal": 0}, {"name": "服务版本回退", "created": 0, "pending": 0, "abnormal": 0}]

export default function Overview() {
  const [cards, setCards] = useState<Overview['cards']>(fallbackCards)
  const [moduleRows, setModuleRows] = useState<Overview['modules']>(fallbackModules)

  useEffect(() => {
    fetchJson<Overview>('/api/overview')
      .then((payload) => {
        setCards(payload.cards)
        setModuleRows(payload.modules)
      })
      .catch(() => undefined)
  }, [])

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h2>运营概览</h2>
          <p className="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
        </div>
      </header>
      <div className="stat-row">
        {cards.map((card) => (
          <article key={card.label} className="stat-card">
            <span className="stat-label">{card.label}</span>
            <strong className="stat-value">{card.value}</strong>
          </article>
        ))}
      </div>
      <table className="data-table">
        <thead>
          <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
        </thead>
        <tbody>
          {moduleRows.map((row) => (
            <tr key={row.name}>
              <td>{row.name}</td>
              <td>{row.created}</td>
              <td>{row.pending}</td>
              <td>{row.abnormal}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
