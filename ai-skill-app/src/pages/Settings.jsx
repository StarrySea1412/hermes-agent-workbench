import { useMemo, useState } from 'react'
import ChatFrame from '../components/chat/ChatFrame'
import GlassSelect from '../components/GlassSelect'
import {
  useAIConfig,
  useCcSwitchProviders,
  useCreateAIConfig,
  useFetchAIModels,
  useHermesMonitor,
  useHermesSkills,
  useImportCcSwitchProvider,
  useTestAIConfig,
  useUpdateAIConfig,
} from '../hooks/useAIConfig'
import './Settings.css'

const DEFAULT_CONFIG = {
  provider: 'openai',
  api_key: '',
  base_url: '',
  model_name: '',
  embedding_model_name: '',
  temperature: 0.7,
  max_tokens: 2000,
}

const PROVIDERS = [
  {
    value: 'openai',
    label: 'OpenAI 兼容接口',
    defaultUrl: '',
    defaultModel: '',
    models: [],
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    defaultUrl: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-chat',
    models: ['deepseek-chat', 'deepseek-reasoner'],
  },
  {
    value: 'qwen',
    label: 'Qwen',
    defaultUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    defaultModel: 'qwen-plus',
    models: ['qwen-max', 'qwen-plus', 'qwen-turbo'],
  },
  {
    value: 'anthropic',
    label: 'Anthropic Claude',
    defaultUrl: 'https://api.anthropic.com',
    defaultModel: 'claude-sonnet-4-20250514',
    models: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-latest'],
  },
  {
    value: 'custom',
    label: '自定义端点',
    defaultUrl: '',
    defaultModel: '',
    models: [],
  },
]

const CUSTOM_MODEL_VALUE = '__custom_model__'

function buildConnectionNotice(result) {
  const details = [
    ['接口地址', result?.endpoint],
    ['模型', result?.model],
    ['错误类型', result?.error_type],
    ['HTTP 状态', result?.status_code],
    ['建议', result?.hint],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '')

  return {
    ok: Boolean(result?.success),
    text: result?.message || '连接测试已完成。',
    details,
    diagnosticText: buildDiagnosticText(result, '模型连接测试'),
  }
}

function buildModelFetchNotice(result, fallback = {}) {
  const success = result?.success !== false
  const details = [
    ['模型列表接口', result?.endpoint],
    ['提供方', result?.provider || fallback.provider],
    ['基础 URL', result?.base_url || fallback.base_url],
    ['模型数量', result?.count],
    ['错误类型', result?.error_type],
    ['HTTP 状态', result?.status_code],
    ['建议', result?.hint],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '')

  return {
    ok: success,
    text: success ? `已获取 ${result?.count || 0} 个模型。` : (result?.message || '获取模型列表失败。'),
    details,
    diagnosticText: buildDiagnosticText(
      {
        ...fallback,
        ...result,
        success,
        endpoint: result?.endpoint || '',
        model: fallback.model_name || result?.model || '',
      },
      '模型列表获取',
    ),
  }
}

function buildDiagnosticText(result, title = '模型诊断') {
  const lines = [
    `AI-skill ${title}`,
    `时间：${new Date().toLocaleString()}`,
    `结果：${result?.success ? '成功' : '失败'}`,
    `消息：${result?.message || ''}`,
    `提供方：${result?.provider || ''}`,
    `基础 URL：${result?.base_url || ''}`,
    `接口地址：${result?.endpoint || ''}`,
    `模型：${result?.model || ''}`,
    `模型数量：${result?.count ?? ''}`,
    `错误类型：${result?.error_type || ''}`,
    `HTTP 状态：${result?.status_code ?? ''}`,
    `建议：${result?.hint || ''}`,
    `原始错误：${result?.error || ''}`,
  ]
  return lines.filter((line) => !line.endsWith('：')).join('\n')
}

async function copyText(text) {
  if (!text) return false
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return true
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(textarea)
  return ok
}

export default function Settings() {
  const { data: existingConfig, isLoading } = useAIConfig()
  const { data: hermesMonitor, isFetching: isMonitorFetching, refetch: refetchHermes } = useHermesMonitor()
  const { data: hermesSkills = [] } = useHermesSkills()
  const createMutation = useCreateAIConfig()
  const updateMutation = useUpdateAIConfig()
  const testMutation = useTestAIConfig()
  const fetchModelsMutation = useFetchAIModels()
  const importCcMutation = useImportCcSwitchProvider()
  const { data: ccSwitch } = useCcSwitchProviders()
  const [edits, setEdits] = useState({})
  const [remoteModels, setRemoteModels] = useState([])
  const [notice, setNotice] = useState(null)
  const [copyState, setCopyState] = useState('')

  const formData = useMemo(() => {
    const base = existingConfig || DEFAULT_CONFIG
    return { ...base, ...edits }
  }, [existingConfig, edits])

  const currentProvider = PROVIDERS.find((provider) => provider.value === formData.provider) || PROVIDERS[0]
  const modelOptions = useMemo(() => {
    const remoteModelIds = remoteModels
      .map((model) => (typeof model === 'string' ? model : model?.id))
      .filter(Boolean)
    const fallbackModels = currentProvider.models
    const availableModels = remoteModelIds.length ? remoteModelIds : fallbackModels
    return Array.from(new Set([...availableModels, formData.model_name].filter(Boolean))).sort()
  }, [currentProvider, formData.model_name, remoteModels])
  const selectedModelOption = modelOptions.includes(formData.model_name) ? formData.model_name : CUSTOM_MODEL_VALUE
  const isSaving = createMutation.isPending || updateMutation.isPending
  const connected = Boolean(hermesMonitor?.connected)

  const saveConfig = async () => {
    const payload = { ...formData }
    if (existingConfig && !payload.api_key) {
      delete payload.api_key
    }
    if (existingConfig) {
      return updateMutation.mutateAsync(payload)
    }
    return createMutation.mutateAsync(payload)
  }

  const handleProviderChange = (provider) => {
    const providerInfo = PROVIDERS.find((item) => item.value === provider)
    setRemoteModels([])
    setEdits((prev) => ({
      ...prev,
      provider,
      base_url: providerInfo?.defaultUrl || '',
      model_name: providerInfo?.defaultModel || '',
    }))
  }

  const handleFetchModels = async () => {
    setNotice(null)
    setCopyState('')
    const apiKey = (formData.api_key || '').trim()
    if (!existingConfig && !apiKey) {
      setNotice({ ok: false, text: '获取模型前请先填写 API Key。' })
      return
    }

    try {
      const payload = {
        provider: formData.provider || currentProvider.value,
        base_url: formData.base_url || currentProvider.defaultUrl,
      }
      if (apiKey) {
        payload.api_key = apiKey
      }
      const result = await fetchModelsMutation.mutateAsync(payload)
      const models = result?.models || []
      const resolvedBaseUrl = result?.endpoint?.replace(/\/models\/?$/, '')
      setRemoteModels(models)
      if (resolvedBaseUrl && resolvedBaseUrl !== formData.base_url) {
        setEdits((prev) => ({ ...prev, base_url: resolvedBaseUrl }))
      }
      if (models.length && !formData.model_name) {
        const firstModel = typeof models[0] === 'string' ? models[0] : models[0]?.id
        if (firstModel) {
          setEdits((prev) => ({ ...prev, model_name: firstModel }))
        }
      }
      setNotice(buildModelFetchNotice({ ...result, count: models.length }, { ...payload, model_name: formData.model_name }))
    } catch (error) {
      setNotice(buildModelFetchNotice(
        error.payload || { success: false, message: error.message || '获取模型列表失败。' },
        {
          provider: formData.provider || currentProvider.value,
          base_url: formData.base_url || currentProvider.defaultUrl,
          model_name: formData.model_name,
        },
      ))
    }
  }

  const remoteModelIds = remoteModels
    .map((model) => (typeof model === 'string' ? model : model?.id))
    .filter(Boolean)

  const applyModel = async (modelName) => {
    if (!existingConfig && !(formData.api_key || '').trim()) {
      setNotice({ ok: false, text: '启用模型前请先填写 API Key。' })
      return
    }
    const payload = { ...formData, model_name: modelName }
    if (existingConfig && !payload.api_key) {
      delete payload.api_key
    }
    try {
      if (existingConfig) {
        await updateMutation.mutateAsync(payload)
      } else {
        await createMutation.mutateAsync(payload)
      }
      setEdits({})
      setNotice({ ok: true, text: `已启用模型：${modelName}` })
    } catch (error) {
      setNotice({ ok: false, text: `启用模型失败：${error.message}` })
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setNotice(null)
    setCopyState('')
    if (!(formData.base_url || '').trim() || !(formData.model_name || '').trim()) {
      setNotice({ ok: false, text: '请先填写基础 URL 和模型名称，或点击“获取模型”后选择模型。' })
      return
    }
    try {
      await saveConfig()
      setEdits({})
      setNotice({ ok: true, text: '配置已保存。' })
    } catch (error) {
      setNotice({ ok: false, text: `保存失败：${error.message}` })
    }
  }

  const handleTest = async () => {
    setNotice(null)
    setCopyState('')
    if (!existingConfig && !formData.api_key) {
      setNotice({ ok: false, text: '测试前请先填写 API Key。' })
      return
    }
    if (!(formData.base_url || '').trim() || !(formData.model_name || '').trim()) {
      setNotice({ ok: false, text: '测试前请先填写基础 URL 和模型名称，或点击“获取模型”后选择模型。' })
      return
    }

    try {
      await saveConfig()
      const result = await testMutation.mutateAsync()
      setNotice(buildConnectionNotice(result))
    } catch (error) {
      if (error.payload?.success === false) {
        setNotice(buildConnectionNotice(error.payload))
      } else {
        setNotice({ ok: false, text: error.message || '连接测试失败。' })
      }
    }
  }

  const handleCopyDiagnostics = async () => {
    if (!notice?.diagnosticText) return
    try {
      const ok = await copyText(notice.diagnosticText)
      setCopyState(ok ? '已复制' : '复制失败')
    } catch {
      setCopyState('复制失败')
    }
  }

  const ccProviders = ccSwitch?.providers || []
  const [ccQuery, setCcQuery] = useState('')
  const filteredCcProviders = ccProviders.filter((provider) => {
    const keyword = ccQuery.trim().toLowerCase()
    if (!keyword) return true
    return (
      provider.name.toLowerCase().includes(keyword) ||
      provider.base_url.toLowerCase().includes(keyword) ||
      (provider.model_name || '').toLowerCase().includes(keyword)
    )
  })
  const handleImportCcProvider = async (provider) => {
    setNotice({ ok: true, text: `正在导入「${provider.name}」...` })
    try {
      const result = await importCcMutation.mutateAsync(provider.id)
      setEdits({})
      setRemoteModels([])
      setNotice({ ok: true, text: result?.message || `已导入并启用：${provider.name}` })
    } catch (error) {
      setNotice({ ok: false, text: error.message || '导入失败。' })
    }
  }

  if (isLoading) {
    return (
      <ChatFrame>
        <main className="page">
          <div className="panel loading-panel">正在加载设置...</div>
        </main>
      </ChatFrame>
    )
  }

  return (
    <ChatFrame>
      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">设置</p>
            <h1>运行时与模型配置</h1>
            <p>配置默认模型提供方，检查 Hermes 连通性，并保持工作台运行健康。</p>
          </div>
        </header>

        <div className="content-grid detail-grid settings-layout">
          <section className="panel">
            <form className="template-editor" onSubmit={handleSubmit}>
              <div className="panel-header">
                <div>
                  <p className="eyebrow">模型接入</p>
                  <h2>提供方配置</h2>
                  <p className="panel-subtext">当前：{formData.model_name || '尚未选择模型'} · {formData.base_url || '未填写接口地址'}</p>
                </div>
              </div>

              <div className="field-grid">
                <div className="field">
                  <span>提供方</span>
                  <GlassSelect
                    ariaLabel="提供方"
                    value={formData.provider}
                    onChange={handleProviderChange}
                    options={PROVIDERS.map((provider) => ({ value: provider.value, label: provider.label }))}
                  />
                </div>

                <div className="field">
                  <span>模型名称</span>
                  <div className="input-action-row">
                    <GlassSelect
                      ariaLabel="模型名称"
                      value={selectedModelOption}
                      onChange={(next) => {
                        if (next === CUSTOM_MODEL_VALUE) return
                        setEdits((prev) => ({ ...prev, model_name: next }))
                      }}
                      options={[
                        ...modelOptions.map((model) => ({ value: model, label: model })),
                        { value: CUSTOM_MODEL_VALUE, label: '自定义模型' },
                      ]}
                    />
                    <input
                      type="text"
                      value={formData.model_name || ''}
                      onChange={(event) => setEdits((prev) => ({ ...prev, model_name: event.target.value }))}
                      placeholder={currentProvider.defaultModel || '输入模型标识'}
                    />
                    <button type="button" className="secondary-button" onClick={handleFetchModels} disabled={fetchModelsMutation.isPending}>
                      {fetchModelsMutation.isPending ? '获取中...' : '获取模型'}
                    </button>
                  </div>
                </div>
              </div>

              <label className="field">
                <span>API key</span>
                <input
                  type="password"
                  value={formData.api_key || ''}
                  onChange={(event) => setEdits((prev) => ({ ...prev, api_key: event.target.value }))}
                  placeholder={existingConfig ? '留空则保留当前 Key。' : '输入提供方 API Key'}
                />
                <small className="inline-hint">Key 只保存在后端，并会在持久化前加密。</small>
              </label>

              <label className="field">
                <span>基础 URL</span>
                <input
                  type="text"
                  value={formData.base_url || ''}
                  onChange={(event) => {
                    setRemoteModels([])
                    setEdits((prev) => ({ ...prev, base_url: event.target.value }))
                  }}
                  placeholder={currentProvider.defaultUrl || '输入 API 基础地址'}
                />
              </label>

              <label className="field">
                <span>向量模型（知识库检索）</span>
                <input
                  type="text"
                  value={formData.embedding_model_name || ''}
                  onChange={(event) => setEdits((prev) => ({ ...prev, embedding_model_name: event.target.value }))}
                  placeholder="如 text-embedding-3-small；留空则资料检索走本地近似向量"
                />
                <small className="inline-hint">上传的资料会用它向量化后供对话自动检索；更换后请到资料页手动重建索引。</small>
              </label>

              {remoteModelIds.length ? (
                <div className="field">
                  <span>可用模型（点击立即启用）</span>
                  <div className="remote-model-grid">
                    {remoteModelIds.map((model) => (
                      <button
                        key={model}
                        type="button"
                        className={`remote-model-chip ${formData.model_name === model ? 'active' : ''}`}
                        disabled={isSaving}
                        onClick={() => applyModel(model)}
                      >
                        {model}
                        {formData.model_name === model ? ' ✓' : ''}
                      </button>
                    ))}
                  </div>
                  <small className="inline-hint">点击模型会立即保存为当前活动配置；保存后可用“测试连接”验证聊天可用性。</small>
                </div>
              ) : null}

              <details className="advanced-config">
                <summary>高级参数（温度 / Token 上限）</summary>
                <div className="field-grid">
                  <label className="field">
                    <span>温度</span>
                    <input
                      className="settings-range"
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={formData.temperature}
                      onChange={(event) => setEdits((prev) => ({ ...prev, temperature: parseFloat(event.target.value) }))}
                    />
                    <small className="inline-hint">当前值：{formData.temperature}</small>
                  </label>

                  <label className="field">
                    <span>最大 Token</span>
                    <input
                      type="number"
                      min="100"
                      max="32000"
                      value={formData.max_tokens}
                      onChange={(event) => setEdits((prev) => ({
                        ...prev,
                        max_tokens: parseInt(event.target.value, 10) || DEFAULT_CONFIG.max_tokens,
                      }))}
                    />
                  </label>
                </div>
              </details>

              {notice ? (
                <div className={`panel-alert ${notice.ok ? '' : 'error'}`}>
                  <div className="panel-alert-header">
                    <strong>{notice.text}</strong>
                    {notice.diagnosticText ? (
                      <button type="button" className="inline-copy-button" onClick={handleCopyDiagnostics}>
                        {copyState || '复制诊断'}
                      </button>
                    ) : null}
                  </div>
                  {notice.details?.length ? (
                    <dl className="diagnostic-list">
                      {notice.details.map(([label, value]) => (
                        <div key={label}>
                          <dt>{label}</dt>
                          <dd>{String(value)}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}
                </div>
              ) : null}

              <div className="editor-actions">
                <button type="button" className="secondary-button" onClick={handleTest} disabled={testMutation.isPending || isSaving}>
                  {testMutation.isPending ? '测试中...' : '测试连接'}
                </button>
                <button type="submit" className="primary-button" disabled={isSaving}>
                  {isSaving ? '保存中...' : '保存配置'}
                </button>
              </div>
            </form>
          </section>

          <aside className="detail-rail">
            <section className="panel cc-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">快速接入</p>
                  <h2>从 CC Switch 导入</h2>
                  <p className="panel-subtext">
                    {ccSwitch?.found
                      ? `本机已发现 ${ccProviders.length} 个供应商。`
                      : '未检测到 CC Switch（~/.cc-switch），请用左侧表单手动配置。'}
                  </p>
                </div>
              </div>
              {ccSwitch?.found ? (
                <>
                  <input
                    type="search"
                    className="cc-search"
                    value={ccQuery}
                    onChange={(event) => setCcQuery(event.target.value)}
                    placeholder="搜索名称 / 地址 / 模型..."
                  />
                  <div className="cc-import-list">
                    {filteredCcProviders.map((provider) => (
                      <article
                        key={provider.id}
                        className={`cc-import-row ${formData.base_url === provider.base_url ? 'active' : ''}`}
                      >
                        <div className="cc-import-info">
                          <strong>{provider.name}</strong>
                          <code>{provider.base_url}</code>
                          <small>
                            {provider.app_type === 'claude' ? 'Claude 协议' : 'OpenAI 兼容'}
                            {provider.model_name ? ` · ${provider.model_name}` : ''}
                            {formData.base_url === provider.base_url ? ' · 当前使用中' : ''}
                          </small>
                        </div>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={importCcMutation.isPending}
                          onClick={() => handleImportCcProvider(provider)}
                        >
                          {importCcMutation.isPending && importCcMutation.variables === provider.id
                            ? '导入中...'
                            : '导入'}
                        </button>
                      </article>
                    ))}
                    {!filteredCcProviders.length ? (
                      <div className="empty-inline">没有匹配「{ccQuery}」的供应商。</div>
                    ) : null}
                  </div>
                  <small className="inline-hint">导入会立即保存为活动配置；重启 AI-skill 后网关生效。</small>
                </>
              ) : null}
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Hermes 监控</p>
                  <h2>网关状态</h2>
                </div>
                <button type="button" className="secondary-button" onClick={() => refetchHermes()} disabled={isMonitorFetching}>
                  {isMonitorFetching ? '刷新中...' : '刷新'}
                </button>
              </div>
              <div className="stack-list">
                <InfoRow label="状态" value={connected ? '已连接' : hermesMonitor?.error || '离线'} />
                <InfoRow label="模型数" value={String(hermesMonitor?.models_count || 0)} />
                <InfoRow label="上次检查" value={formatDate(hermesMonitor?.checked_at)} />
              </div>
              {hermesMonitor?.models?.length ? (
                <div className="chip-list">
                  {hermesMonitor.models.map((model) => (
                    <code key={model}>{model}</code>
                  ))}
                </div>
              ) : null}
            </section>

            <details className="panel skill-panel">
              <summary className="panel-header">
                <div>
                  <p className="eyebrow">技能</p>
                  <h2>本地技能清单（{hermesSkills.length}）</h2>
                </div>
              </summary>
              <div className="skill-card-grid">
                {hermesSkills.slice(0, 6).map((skill) => (
                  <article key={skill.path} className="skill-card">
                    <div className="skill-card-top">
                      <strong>{skill.title || skill.name}</strong>
                      <small>{skill.source}</small>
                    </div>
                    <code>{skill.path}</code>
                    <p>{skill.description || '暂无描述。'}</p>
                  </article>
                ))}
                {!hermesSkills.length ? <div className="empty-inline">还没有发现本地技能。</div> : null}
              </div>
            </details>

            <details className="panel">
              <summary className="panel-header">
                <div>
                  <p className="eyebrow">运行说明</p>
                  <h2>这份配置会影响什么</h2>
                </div>
              </summary>
              <div className="stack-list">
                <InfoRow label="通用内容" value="模型配置会影响兼容模式下的内容生成和相关导出。" />
                <InfoRow label="智能体工作台" value="基于 Hermes 的智能体运行会优先使用 Hermes 网关，而不是这里的提供方表单。" />
                <InfoRow label="本地技能" value="模板会引用从 hermes_skills/ 目录发现的技能路径。" />
              </div>
            </details>
          </aside>
        </div>
      </main>
    </ChatFrame>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <p>{value}</p>
    </div>
  )
}

function formatDate(value) {
  if (!value) return '暂无'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}
