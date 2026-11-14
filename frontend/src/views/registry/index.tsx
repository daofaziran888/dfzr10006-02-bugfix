import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/registry'
const columns = [
  "实例编号",
  "服务名称",
  "服务版本",
  "注册版本",
  "服务地址",
  "注册时间",
  "心跳间隔",
  "健康状态",
  "实例标签"
]
// 动作 -> 执行该动作所要求的当前状态；与后端状态机口径保持一致
const actionPrecondition: Record<string, string> = {
  "上线服务": "草稿",
  "下线服务": "已注册",
  "注销服务": "已下线",
}
const actions = Object.keys(actionPrecondition)
const statuses = ["草稿", "已注册", "已下线", "已注销"]

type Row = Record<string, string | number | null>
type Receipt = { ok: boolean; message: string }
type ActionLog = {
  id: number
  动作: string
  from_status: string
  to_status: string
  注册版本: number
  ok: boolean
  回执: string
  时间: string
}

function statusBadge(status: string) {
  return <span className={`badge badge-${statuses.indexOf(status)}`}>{status}</span>
}

export default function RegistryView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [inFlight, setInFlight] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [detail, setDetail] = useState<Row | null>(null)
  const [actionLogs, setActionLogs] = useState<ActionLog[]>([])
  const filterFields = useMemo(() => columns.slice(0, 3), [])

  const stats = useMemo(() => [
    { label: "服务实例总数", value: rows.length },
    { label: "已注册实例", value: rows.filter((row) => row.status === "已注册").length },
    { label: "已下线实例", value: rows.filter((row) => row.status === "已下线").length },
    { label: "已注销实例", value: rows.filter((row) => row.status === "已注销").length },
  ], [rows])

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('服务实例列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '服务注册发现列表读取失败')
    }
  }, [filters])

  useEffect(() => {
    void reload()
  }, [reload])

  async function runAction(action: string, row: Row) {
    // 前端门控：非法动作按钮本就禁用，这里再拦一次，避免非法动作发出请求
    if (row.status !== actionPrecondition[action]) {
      setReceipt({ ok: false, message: `当前状态为「${row.status}」，不能执行${action}，记录保持不变` })
      return
    }
    const actionKey = `${row.id}-${action}`
    if (inFlight) {
      return
    }
    setInFlight(actionKey)
    setErrorMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ values: { action } }),
      })
      if (!response.ok) {
        throw new Error('服务注册发现动作未生效，请稍后重试')
      }
      const payload = await response.json()
      // 以业务回执为准：ok=false 时状态未变，不能再当成成功提示
      setReceipt({ ok: Boolean(payload.ok), message: payload.message ?? '动作已提交' })
      await reload()
    } catch (error) {
      setReceipt({ ok: false, message: error instanceof Error ? error.message : '服务注册发现操作失败' })
    } finally {
      setInFlight('')
    }
  }

  async function openDetail(row: Row) {
    setDetail(row)
    setActionLogs([])
    try {
      const response = await request(`${ENDPOINT}/${row.id}/action-logs`)
      if (!response.ok) {
        throw new Error('动作记录读取失败')
      }
      const payload = await response.json()
      setActionLogs(payload.items ?? [])
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '实例动作记录读取失败')
    }
  }

  return (
    <section className="page" data-module="registry">
      <header className="page-head">
        <div>
          <h2>服务注册发现管理</h2>
          <p className="page-desc">维护数据服务的注册信息、版本管理与健康监测，实例按 草稿 → 已注册 → 已下线 → 已注销 单向推进，路由灰度入口随注册状态联动。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setErrorMessage('服务实例登记入口尚未接入审批流')}>
            登记服务实例
          </button>
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出服务注册发现清单
          </button>
        </div>
      </header>

      <div className="stat-row">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
          </article>
        ))}
      </div>

      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reload() }}>
        {filterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={filters[field] ?? ''}
              placeholder={`按${field}检索`}
              onChange={(event) => setFilters((prev) => ({ ...prev, [field]: event.target.value }))}
            />
          </label>
        ))}
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({})}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>注册状态</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}
              <td>{statusBadge(String(row.status ?? ''))}</td>
              <td className="row-actions">
                {actions.map((action) => {
                  const allowed = row.status === actionPrecondition[action]
                  const busy = inFlight === `${row.id}-${action}`
                  return (
                    <button
                      key={action}
                      className="link"
                      type="button"
                      disabled={!allowed || Boolean(inFlight)}
                      title={allowed ? action : `仅「${actionPrecondition[action]}」状态可执行${action}`}
                      onClick={() => void runAction(action, row)}
                    >
                      {busy ? `${action}中…` : action}
                    </button>
                  )
                })}
                <button className="link" type="button" onClick={() => void openDetail(row)}>动作记录</button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 2}>暂无服务注册发现数据，可先登记服务实例</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条服务注册发现记录</span>
        {receipt && (
          <span className={receipt.ok ? 'receipt-text' : 'error-text'} role="status">
            {receipt.ok ? '✓ ' : '✕ '}{receipt.message}
          </span>
        )}
        {!receipt && errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>

      {detail && (
        <div className="drawer-mask" onClick={() => setDetail(null)}>
          <aside className="drawer" onClick={(event) => event.stopPropagation()}>
            <header className="drawer-head">
              <h3>实例动作记录 · {String(detail['实例编号'])}</h3>
              <button className="btn ghost" type="button" onClick={() => setDetail(null)}>关闭</button>
            </header>
            <dl className="detail-grid">
              <div><dt>服务名称</dt><dd>{String(detail['服务名称'] ?? '—')}</dd></div>
              <div><dt>实例编号</dt><dd>{String(detail['实例编号'] ?? '—')}</dd></div>
              <div><dt>注册版本</dt><dd>{String(detail['注册版本'] ?? '0')}</dd></div>
              <div><dt>服务地址</dt><dd>{String(detail['服务地址'] ?? '—')}</dd></div>
              <div><dt>健康状态</dt><dd>{String(detail['健康状态'] ?? '—')}</dd></div>
              <div><dt>注册状态</dt><dd>{String(detail.status ?? '—')}</dd></div>
            </dl>
            <table className="data-table">
              <thead>
                <tr><th>时间</th><th>动作</th><th>状态变化</th><th>注册版本</th><th>回执</th></tr>
              </thead>
              <tbody>
                {actionLogs.map((log) => (
                  <tr key={log.id} className={log.ok ? '' : 'row-failed'}>
                    <td>{log.时间}</td>
                    <td>{log.动作}</td>
                    <td>{log.from_status} → {log.to_status}</td>
                    <td>v{log.注册版本}</td>
                    <td>
                      <span className={log.ok ? 'receipt-text' : 'error-text'}>
                        {log.ok ? '成功' : '失败'}：{log.回执}
                      </span>
                    </td>
                  </tr>
                ))}
                {actionLogs.length === 0 && (
                  <tr><td className="empty-state" colSpan={5}>暂无动作记录</td></tr>
                )}
              </tbody>
            </table>
          </aside>
        </div>
      )}
    </section>
  )
}
