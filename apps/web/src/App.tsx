import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";
import { api, mutate, setCsrf } from "./api";

type Page = "dashboard" | "accounts" | "sources" | "ai" | "tasks" | "reports" | "system";
type Source = { id: number; platform: string; chat_type: string; title: string; enabled: boolean; status: string; last_seen_at: number; folders: string[] };
type Target = { id: number; name: string; enabled: boolean; type: string };
type Task = { id: number; name: string; enabled: boolean; schedule_type: string; schedule_hour: number; schedule_minute: number; timezone: string; source_ids: number[]; delivery_target_ids: number[]; prompt_mode: "adaptive" | "custom"; report_prompt: string };
type Report = { id: number; title: string; created_at: number; message_count: number; ai_status: string };
type System = { core: string; collectors: { id: string; platform: string; status: string; last_seen_at: number }[]; counts: Record<string, number> };
type TelegramStatus = { authorization_state: string; qr_link?: string; username?: string; display_name?: string; chat_count: number; last_error?: string };

const NAV: { id: Page; mark: string; label: string }[] = [
  { id: "dashboard", mark: "01", label: "总览" },
  { id: "accounts", mark: "02", label: "账号" },
  { id: "sources", mark: "03", label: "消息源" },
  { id: "ai", mark: "04", label: "AI 与飞书" },
  { id: "tasks", mark: "05", label: "报告任务" },
  { id: "reports", mark: "06", label: "报告历史" },
  { id: "system", mark: "07", label: "系统状态" },
];

type ModelPreset = { provider: string; value: string; label: string; baseUrl: string };
type PlatformLink = { name: string; href: string; baseUrl: string; note: string };

const MODEL_PRESETS: readonly ModelPreset[] = [
  { provider: "OpenAI", value: "gpt-5", label: "GPT-5 · 通用", baseUrl: "https://api.openai.com/v1" },
  { provider: "OpenAI", value: "gpt-5-mini", label: "GPT-5 mini · 性价比", baseUrl: "https://api.openai.com/v1" },
  { provider: "OpenAI", value: "gpt-5-nano", label: "GPT-5 nano · 低成本", baseUrl: "https://api.openai.com/v1" },
  { provider: "DeepSeek", value: "deepseek-v4-pro", label: "DeepSeek V4 Pro · 高质量", baseUrl: "https://api.deepseek.com" },
  { provider: "DeepSeek", value: "deepseek-v4-flash", label: "DeepSeek V4 Flash · 快速", baseUrl: "https://api.deepseek.com" },
  { provider: "通义千问", value: "qwen-plus", label: "Qwen Plus · 均衡", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { provider: "通义千问", value: "qwen-max", label: "Qwen Max · 高质量", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { provider: "腾讯混元", value: "hy3-preview", label: "Hunyuan Hy3 · 预览", baseUrl: "https://tokenhub.tencentmaas.com/v1" },
];

const PLATFORM_LINKS: readonly PlatformLink[] = [
  { name: "OpenAI Platform", href: "https://platform.openai.com/", baseUrl: "https://api.openai.com/v1", note: "GPT 系列" },
  { name: "DeepSeek 开放平台", href: "https://platform.deepseek.com/", baseUrl: "https://api.deepseek.com", note: "DeepSeek V4" },
  { name: "阿里云百炼", href: "https://bailian.console.aliyun.com/", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", note: "通义千问" },
  { name: "腾讯混元 TokenHub", href: "https://cloud.tencent.com/document/product/1729/111007", baseUrl: "https://tokenhub.tencentmaas.com/v1", note: "混元 Hy3" },
];

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="empty"><i>∅</i><p>{children}</p></div>;
}

function StatusDot({ value }: { value: string }) {
  const healthy = ["healthy", "online", "Ready", "success"].includes(value);
  return <span className={`status ${healthy ? "ok" : "warn"}`}><i />{value}</span>;
}

function Auth({ setup, onReady }: { setup: boolean; onReady: () => void }) {
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (setup && !done) {
        await mutate("/api/v1/setup", "POST", data); setDone(true); return;
      }
      const result = await mutate<{ csrf_token: string }>("/api/v1/auth/login", "POST", data);
      setCsrf(result.csrf_token); onReady();
    } catch (cause) { setError((cause as Error).message); }
  }
  const isSetup = setup && !done;
  return <main className="auth-shell">
    <section className="auth-brand"><span className="eyebrow">SELF-HOSTED INTELLIGENCE</span><h1>Chat<br/><em>Insight</em></h1><p>从喧闹的群聊里，提取真正需要被看见的信号。</p><div className="signal-lines" /></section>
    <section className="auth-panel"><div><span className="edition">VOL. 01 / 2026</span><h2>{isSetup ? "建立控制席" : "返回情报台"}</h2><p>{isSetup ? "一次性 Setup Token 使用后立即失效。" : "使用管理员账号继续。"}</p></div>
      <form onSubmit={submit}>
        {isSetup && <Field label="SETUP TOKEN"><input name="setup_token" type="password" required autoFocus /></Field>}
        <Field label="管理员账号"><input name="username" required autoFocus={!isSetup} autoComplete="username" /></Field>
        <Field label="密码"><input name="password" type="password" minLength={isSetup ? 12 : 1} required autoComplete={isSetup ? "new-password" : "current-password"} /></Field>
        {error && <p className="error">{error}</p>}<button className="primary" type="submit">{isSetup ? "创建管理员 →" : "进入控制台 →"}</button>
      </form>
    </section>
  </main>;
}

function Dashboard({ system, sources, reports }: { system?: System; sources: Source[]; reports: Report[] }) {
  const enabled = sources.filter(x => x.enabled).length;
  return <><header className="page-head"><div><span className="kicker">DAILY SIGNAL BOARD</span><h1>今天，群聊里<br/>发生了什么？</h1></div><div className="date-block"><strong>{new Date().getDate().toString().padStart(2,"0")}</strong><span>{new Intl.DateTimeFormat("zh-CN", { month:"long", year:"numeric" }).format(new Date())}</span></div></header>
    <section className="metrics"><article><span>已接入账号</span><strong>{system?.counts.accounts ?? 0}</strong><small>ACCOUNTS</small></article><article className="accent"><span>正在监听</span><strong>{enabled}</strong><small>ACTIVE SOURCES</small></article><article><span>累计报告</span><strong>{reports.length}</strong><small>REPORTS</small></article><article><span>Core</span><strong className="word">{system?.core ?? "—"}</strong><small>SYSTEM</small></article></section>
    <section className="two-col"><article className="paper"><div className="section-title"><span>01</span><h2>最新报告</h2></div>{reports.length ? reports.slice(0,5).map(x => <div className="report-row" key={x.id}><time>{new Date(x.created_at).toLocaleString("zh-CN")}</time><b>{x.title}</b><span>{x.message_count} 条</span></div>) : <Empty>报告生成后会在这里形成时间轴。</Empty>}</article>
      <article className="ink-card"><div className="section-title"><span>02</span><h2>信号覆盖</h2></div><div className="coverage"><b>{sources.length || 0}</b><span>个已发现来源</span><div className="bar"><i style={{width: `${sources.length ? enabled/sources.length*100 : 0}%`}} /></div><small>{enabled} 个已明确授权采集 · 默认关闭保护隐私</small></div></article></section></>;
}

function Accounts() {
  const [status, setStatus] = useState<TelegramStatus>(); const [qr, setQr] = useState(""); const [error, setError] = useState("");
  const ready = status?.authorization_state === "Ready";
  const refresh = useCallback(async () => { try { const data = await api<TelegramStatus>("/api/v1/telegram/auth/status"); setStatus(data); if(data.qr_link) setQr(await QRCode.toDataURL(data.qr_link,{width:240,margin:1,color:{dark:"#171912",light:"#f3f0e6"}})); else setQr(""); } catch(cause){ setError((cause as Error).message); } },[]);
  useEffect(() => { refresh(); const timer=setInterval(refresh,3000); return ()=>clearInterval(timer); },[refresh]);
  async function config(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setError(""); const form=event.currentTarget; const data=Object.fromEntries(new FormData(form)); try { await mutate("/api/v1/telegram/config","PUT",{api_id:Number(data.telegram_api_id),api_hash:data.telegram_api_hash}); form.reset(); await refresh(); } catch(cause) { setError((cause as Error).message); } }
  async function generateQr() { setError(""); setQr(""); try { await mutate("/api/v1/telegram/auth/qr","POST",{}); await refresh(); } catch(cause) { setError((cause as Error).message); } }
  async function value(event: FormEvent<HTMLFormElement>, action:string) { event.preventDefault(); setError(""); const form=event.currentTarget; const data=Object.fromEntries(new FormData(form)); try { await mutate(`/api/v1/telegram/auth/${action}`,"POST",{value:data.value}); form.reset(); await refresh(); } catch(cause) { setError((cause as Error).message); } }
  return <><header className="compact-head"><span className="kicker">ACCOUNTS / PERSONAL ACCESS</span><h1>账号接入</h1><p>凭据只保存在你的服务器；消息源仍需逐个启用。</p></header><section className="account-grid"><article className="account-card telegram"><div className="platform"><b>TELEGRAM</b><StatusDot value={status?.authorization_state ?? "offline"}/></div><h2>{status?.username ? `@${status.username}` : status?.display_name || "个人账号"}</h2><p>{status?.chat_count || 0} 个会话已发现</p>{qr && <img className="qr" src={qr} alt="Telegram 登录二维码" />}
    {ready ? <p className="success">Telegram 已连接；正在发现群组和频道。</p> : <><form className="inline-form" autoComplete="off" onSubmit={config}><Field label="API ID"><input name="telegram_api_id" type="tel" autoComplete="off" inputMode="numeric" required /></Field><Field label="API HASH"><input name="telegram_api_hash" type="password" autoComplete="new-password" required /></Field><button>保存连接</button></form>
    <div className="auth-actions"><button type="button" onClick={generateQr}>生成 QR</button><details><summary>使用手机号</summary><form autoComplete="off" onSubmit={e=>value(e,"phone")}><input name="value" autoComplete="tel" placeholder="+86…" required/><button>提交</button></form></details><details><summary>验证码 / 2FA</summary><form autoComplete="off" onSubmit={e=>value(e,"code")}><input name="value" autoComplete="one-time-code" placeholder="验证码" required/><button>验证</button></form><form autoComplete="off" onSubmit={e=>value(e,"password")}><input name="value" type="password" autoComplete="current-password" placeholder="两步验证密码" required/><button>验证</button></form></details></div></>}{error && <p className="error">{error}</p>}</article>
    <article className="account-card qq"><div className="platform"><b>QQ / ONEBOT</b><span className="status warn"><i/>由 AstrBot 上报</span></div><h2>NapCat + AstrBot</h2><p>安装仓库内 QQ Adapter 后，群列表和连接状态会自动出现。</p><ol><li>NapCat 连接 AstrBot OneBot v11</li><li>配置同一 Collector Token</li><li>回到“消息源”明确启用群</li></ol></article></section></>;
}

function Sources({ values, reload }: { values: Source[]; reload: () => void }) {
  const [filter,setFilter]=useState("all"); const [folder,setFolder]=useState("all"); const [changing,setChanging]=useState(false); const folders=[...new Set(values.filter(x=>x.platform==="telegram").flatMap(x=>x.folders))].sort(); const shown=values.filter(x=>(filter==="all"||x.platform===filter)&&(folder==="all"||x.folders.includes(folder))); const groupSources=shown.filter(x=>x.platform==="telegram"&&x.status!=="migrated"); const groupName=folder==="all"?"所有 Telegram 来源":`“${folder}”分组`;
  async function toggle(item:Source){ await mutate(`/api/v1/sources/${item.id}`,"PATCH",{enabled:!item.enabled}); reload(); }
  async function toggleGroup(enabled:boolean){if(!groupSources.length||!window.confirm(`确定${enabled?"开启采集":"关闭"}${groupName}内的 ${groupSources.length} 个来源吗？`))return;setChanging(true);try{await mutate("/api/v1/sources:batch","PATCH",{source_ids:groupSources.map(x=>x.id),enabled});await reload();}finally{setChanging(false);}}
  return <><header className="compact-head"><span className="kicker">SOURCE CONSENT</span><h1>消息源</h1><p>发现不等于采集。只有开启的来源才会持久化并进入报告。</p></header><div className="toolbar"><button className={filter==="all"?"selected":""} onClick={()=>{setFilter("all");setFolder("all")}}>全部 {values.length}</button><button className={filter==="qq"?"selected":""} onClick={()=>{setFilter("qq");setFolder("all")}}>QQ</button><button className={filter==="telegram"?"selected":""} onClick={()=>setFilter("telegram")}>Telegram</button></div>{(filter==="telegram"||filter==="all")&&folders.length>0&&<div className="toolbar source-folders"><span className="folder-label">Telegram 分组</span><button className={folder==="all"?"selected":""} onClick={()=>setFolder("all")}>全部</button>{folders.map(name=><button className={folder===name?"selected":""} key={name} onClick={()=>{setFilter("telegram");setFolder(name)}}>{name}</button>)}{filter==="telegram"&&<span className="folder-actions"><button className="primary" disabled={changing||!groupSources.some(x=>!x.enabled)} onClick={()=>void toggleGroup(true)}>全选并开启</button><button disabled={changing||!groupSources.some(x=>x.enabled)} onClick={()=>void toggleGroup(false)}>全部关闭</button></span>}</div>}<section className="source-list">{shown.length ? shown.map(item=><article key={item.id}><div className="source-mark">{item.platform==="qq"?"Q":"T"}</div><div><b>{item.title||item.id}</b><span>{item.platform} · {item.chat_type}{item.folders.length?` · ${item.folders.join(" / ")}`:""}</span></div><StatusDot value={item.status}/><label className="switch"><input type="checkbox" checked={item.enabled&&item.status!=="migrated"} disabled={item.status==="migrated"} onChange={()=>toggle(item)}/><i/><span>{item.status==="migrated"?"已迁移":item.enabled?"采集中":"已关闭"}</span></label></article>) : <Empty>Collector 登录后会自动发现可用群与频道。</Empty>}</section></>;
}

function AIAndDelivery({ targets, reload }: { targets: Target[]; reload:()=>void }) {
  const [message,setMessage]=useState("");
  const [baseUrl,setBaseUrl]=useState("https://api.openai.com/v1");
  const [model,setModel]=useState("gpt-5-mini");
  async function saveAI(e:FormEvent<HTMLFormElement>){e.preventDefault();const d=Object.fromEntries(new FormData(e.currentTarget));await mutate("/api/v1/settings/ai","PUT",{enabled:true,base_url:d.ai_base_url,api_key:d.ai_access_token||null,model:d.ai_model,max_input_chars:60000});setMessage("AI 配置已加密保存");}
  async function addTarget(e:FormEvent<HTMLFormElement>){e.preventDefault();const d=Object.fromEntries(new FormData(e.currentTarget));await mutate("/api/v1/delivery-targets","POST",{name:d.feishu_target_name,webhook:d.feishu_webhook_url,secret:d.feishu_signing_key||null});e.currentTarget.reset();reload();}
  async function removeTarget(target:Target){if(!window.confirm(`删除飞书目标“${target.name}”？关联的报告任务将不再向该目标推送。`))return;await mutate(`/api/v1/delivery-targets/${target.id}`,"DELETE");reload();}
  function chooseModel(value:string){setModel(value);const preset=MODEL_PRESETS.find(item=>item.value===value);if(preset)setBaseUrl(preset.baseUrl);}
  return <><header className="compact-head"><span className="kicker">ANALYSIS & DELIVERY</span><h1>AI 与飞书</h1><p>模型只收到被选中的文本，不具备工具，也不会接触内部用户 ID。</p></header><section className="settings-grid"><div className="ai-stack"><form className="paper form-card" onSubmit={saveAI} autoComplete="off"><div className="section-title"><span>AI</span><h2>OpenAI Compatible</h2></div><Field label="BASE URL"><input name="ai_base_url" value={baseUrl} onChange={e=>setBaseUrl(e.target.value)} autoComplete="off" spellCheck={false} required /></Field><Field label="MODEL" hint="选择预设会同步填入兼容地址；也可手动输入模型 ID"><input name="ai_model" list="model-presets" value={model} onChange={e=>chooseModel(e.target.value)} autoComplete="off" spellCheck={false} required /><datalist id="model-presets">{MODEL_PRESETS.map(item=><option key={item.value} value={item.value} label={`${item.provider} · ${item.label}`}/>)}</datalist></Field><Field label="API KEY" hint="留空不会覆盖已有密钥"><input name="ai_access_token" type="password" autoComplete="section-ai new-password" /></Field><button className="primary">保存 AI 配置</button>{message&&<p className="success">{message}</p>}</form><section className="platform-directory" aria-labelledby="platform-directory-title"><div><span className="kicker">OPEN PLATFORM</span><h2 id="platform-directory-title">模型开放平台</h2><p>选择模型后会自动填入对应 Base URL；从官方平台创建 API Key。</p></div><div className="platform-links">{PLATFORM_LINKS.map(platform=><a key={platform.name} href={platform.href} target="_blank" rel="noreferrer"><span>{platform.note}</span><b>{platform.name} ↗</b><code>{platform.baseUrl}</code></a>)}</div></section></div>
  <form className="ink-card form-card" onSubmit={addTarget} autoComplete="off"><div className="section-title"><span>飞</span><h2>飞书目标</h2></div><Field label="名称"><input name="feishu_target_name" placeholder="运营群" autoComplete="off" required /></Field><Field label="WEBHOOK"><input name="feishu_webhook_url" type="url" autoComplete="off" spellCheck={false} required /></Field><Field label="SIGN SECRET"><input name="feishu_signing_key" type="password" autoComplete="section-feishu new-password" /></Field><button>新增推送目标</button><div className="chips">{targets.map(x=><span key={x.id}>{x.name}<button type="button" onClick={()=>void removeTarget(x)} aria-label={`删除飞书目标 ${x.name}`}>删除 ×</button></span>)}</div></form></section></>;
}

function Tasks({ sources, targets, tasks, reload }: { sources:Source[];targets:Target[];tasks:Task[];reload:()=>void }) {
  const [saving,setSaving]=useState(false); const [message,setMessage]=useState(""); const [error,setError]=useState(""); const [editing,setEditing]=useState<Task>(); const [promptMode,setPromptMode]=useState<Task["prompt_mode"]>("adaptive");
  function beginEdit(task:Task){setEditing(task);setPromptMode(task.prompt_mode);setMessage("");setError("");}
  function cancelEdit(){setEditing(undefined);setPromptMode("adaptive");setMessage("");setError("");}
  async function removeTask(task:Task){if(!window.confirm(`删除报告任务“${task.name}”？其运行记录、历史报告和投递日志将一并删除，且无法恢复。`))return;setSaving(true);setMessage("");setError("");try{await mutate(`/api/v1/report-tasks/${task.id}`,"DELETE");if(editing?.id===task.id)cancelEdit();await reload();setMessage("报告任务已删除");}catch(cause){setError((cause as Error).message);}finally{setSaving(false);}}
  async function save(e:FormEvent<HTMLFormElement>){
    e.preventDefault(); if(saving)return; const element=e.currentTarget; const form=new FormData(element); const sourceIds=form.getAll("sources").map(Number); const targetIds=form.getAll("targets").map(Number);
    setMessage("");setError("");if(!sourceIds.length||!targetIds.length){setError("请至少选择一个来源和一个飞书目标");return;}setSaving(true);
    const payload={name:String(form.get("name")||""),enabled:form.get("enabled")==="on",source_ids:sourceIds,schedule_type:form.get("schedule_type"),schedule_hour:Number(form.get("hour")),schedule_minute:Number(form.get("minute")),timezone:form.get("timezone"),delivery_target_ids:targetIds,prompt_mode:promptMode,report_prompt:String(form.get("report_prompt")||"")};
    try{await mutate(editing?`/api/v1/report-tasks/${editing.id}`:"/api/v1/report-tasks",editing?"PUT":"POST",payload);await reload();setMessage(editing?"报告任务已更新":"报告任务已创建");setEditing(undefined);setPromptMode("adaptive");element.reset();}
    catch(cause){setError((cause as Error).message);}finally{setSaving(false);}
  }
  const submitLabel=editing?"保存修改 →":"创建任务 →";
  return <><header className="compact-head"><span className="kicker">REPORT AUTOMATION</span><h1>报告任务</h1><p>来源、自然时间窗口、报告控制提示词和投递目标被绑定为一个可审计任务。</p></header><section className="task-layout"><form key={editing?.id??"new"} className="paper task-form" onSubmit={save}><div className="form-heading"><b>{editing?"编辑任务":"新建任务"}</b>{editing&&<button type="button" className="text-button" onClick={cancelEdit}>取消编辑</button>}</div><Field label="任务名称"><input name="name" placeholder="全平台 AI 日报" defaultValue={editing?.name} required/></Field><label className="task-enabled"><input name="enabled" type="checkbox" defaultChecked={editing?.enabled??true}/><span>启用此任务</span></label><div className="choice-block"><b>01 / 选择来源</b>{sources.filter(x=>x.enabled).map(x=><label key={x.id}><input type="checkbox" name="sources" value={x.id} defaultChecked={editing?.source_ids.includes(x.id)}/><span>{x.title}</span><small>{x.platform}</small></label>)}</div><div className="form-row"><Field label="周期"><select name="schedule_type" defaultValue={editing?.schedule_type??"daily"}><option value="daily">日报</option><option value="hourly">小时报</option></select></Field><Field label="小时"><input name="hour" type="number" min="0" max="23" defaultValue={editing?.schedule_hour??23}/></Field><Field label="分钟"><input name="minute" type="number" min="0" max="59" defaultValue={editing?.schedule_minute??55}/></Field></div><Field label="时区"><input name="timezone" defaultValue={editing?.timezone??"Asia/Shanghai"} required/></Field><fieldset className="prompt-control"><legend>02 / 报告控制提示词</legend><p>提示词只约束本任务的报告重点；聊天消息始终作为不可信原始数据处理。</p><label><input type="radio" name="prompt_mode" value="adaptive" checked={promptMode==="adaptive"} onChange={()=>setPromptMode("adaptive")}/><span><b>自适应</b><small>每次根据本次原始消息、来源分布与关键词自动调整分析重点。</small></span></label><label><input type="radio" name="prompt_mode" value="custom" checked={promptMode==="custom"} onChange={()=>setPromptMode("custom")}/><span><b>自定义</b><small>由你定义报告的关注角度、语气或输出优先级。</small></span></label>{promptMode==="custom"&&<textarea name="report_prompt" defaultValue={editing?.report_prompt} maxLength={4000} placeholder="例如：优先总结产品反馈和购买意向；按紧急程度列出待跟进事项。" required aria-label="自定义报告控制提示词"/>}</fieldset><div className="choice-block"><b>03 / 飞书目标</b>{targets.map(x=><label key={x.id}><input type="checkbox" name="targets" value={x.id} defaultChecked={editing?.delivery_target_ids.includes(x.id)}/><span>{x.name}</span></label>)}</div><button className="primary" disabled={saving}>{saving?"正在保存…":submitLabel}</button>{message&&<p className="success">{message}</p>}{error&&<p className="error">{error}</p>}</form><div className="task-stack">{tasks.length?tasks.map((x,i)=><article key={x.id}><span className="task-no">{String(i+1).padStart(2,"0")}</span><div><b>{x.name}</b><p>{x.schedule_type==="daily"?`每日 ${String(x.schedule_hour).padStart(2,"0")}:${String(x.schedule_minute).padStart(2,"0")}`:`每小时 :${String(x.schedule_minute).padStart(2,"0")}`} · {x.timezone}</p><small className="task-prompt">{x.prompt_mode==="custom"?"自定义提示词":"自适应提示词"}</small></div><div className="task-state"><StatusDot value={x.enabled?"online":"disabled"}/><button type="button" className="secondary" onClick={()=>beginEdit(x)} aria-label={`编辑报告任务 ${x.name}`}>编辑</button><button type="button" className="secondary danger-button" onClick={()=>void removeTask(x)} disabled={saving} aria-label={`删除报告任务 ${x.name}`}>删除</button></div></article>):<Empty>选择至少一个已启用来源来创建任务。</Empty>}</div></section></>;
}

function Reports({ reports }: { reports:Report[] }) { const [detail,setDetail]=useState<{title:string;markdown:string}>(); return <><header className="compact-head"><span className="kicker">ARCHIVE / IMMUTABLE</span><h1>报告历史</h1><p>每个自然时间窗口只生成一次，历史不会被静默覆盖。</p></header><section className="report-archive">{reports.length?reports.map(x=><button key={x.id} onClick={()=>api(`/api/v1/reports/${x.id}`).then(data=>setDetail(data as {title:string;markdown:string}))}><time>{new Date(x.created_at).toLocaleDateString("zh-CN")}</time><b>{x.title}</b><span>{x.message_count} 条 / {x.ai_status}</span><i>↗</i></button>):<Empty>暂无报告。</Empty>}</section>{detail&&<div className="modal" role="dialog" aria-modal="true"><article><button className="close" onClick={()=>setDetail(undefined)}>关闭 ×</button><h2>{detail.title}</h2><pre>{detail.markdown}</pre></article></div>}</> }

function SystemPage({system}:{system?:System}) { return <><header className="compact-head"><span className="kicker">OPERATIONS</span><h1>系统状态</h1><p>Collector 单点离线不会停止其他平台和 Core。</p></header><section className="system-board"><article><span>CORE</span><StatusDot value={system?.core??"unknown"}/><p>SQLite 单写者 · API · Scheduler</p></article>{system?.collectors.map(x=><article key={x.id}><span>{x.platform.toUpperCase()}</span><StatusDot value={x.status}/><p>最近心跳 {new Date(x.last_seen_at).toLocaleTimeString("zh-CN")}</p></article>)}</section></> }

export default function App() {
  const [phase,setPhase]=useState<"loading"|"setup"|"login"|"app">("loading"); const [page,setPage]=useState<Page>("dashboard"); const [error,setError]=useState("");
  const [sources,setSources]=useState<Source[]>([]);const [targets,setTargets]=useState<Target[]>([]);const [tasks,setTasks]=useState<Task[]>([]);const [reports,setReports]=useState<Report[]>([]);const [system,setSystem]=useState<System>();
  const bootstrap=useCallback(async()=>{try{const setup=await api<{required:boolean}>("/api/v1/setup/status");if(setup.required){setPhase("setup");return;}const me=await api<{csrf_token:string}>("/api/v1/auth/me");setCsrf(me.csrf_token);setPhase("app");}catch{setPhase("login");}},[]);
  const reload=useCallback(async()=>{if(phase!=="app")return;try{const [s,t,k,r,y]=await Promise.all([api<Source[]>("/api/v1/sources"),api<Target[]>("/api/v1/delivery-targets"),api<Task[]>("/api/v1/report-tasks"),api<Report[]>("/api/v1/reports"),api<System>("/api/v1/system/status")]);setSources(s);setTargets(t);setTasks(k);setReports(r);setSystem(y);setError("");}catch(cause){setError((cause as Error).message);}},[phase]);
  useEffect(()=>{bootstrap();},[bootstrap]);useEffect(()=>{reload();},[reload]);
  const content=useMemo(()=>({dashboard:<Dashboard system={system} sources={sources} reports={reports}/>,accounts:<Accounts/>,sources:<Sources values={sources} reload={reload}/>,ai:<AIAndDelivery targets={targets} reload={reload}/>,tasks:<Tasks sources={sources} targets={targets} tasks={tasks} reload={reload}/>,reports:<Reports reports={reports}/>,system:<SystemPage system={system}/>} satisfies Record<Page,ReactNode>),[page,system,sources,reports,targets,tasks,reload]);
  if(phase==="loading")return <div className="loader"><i/><span>正在校准信号</span></div>;if(phase==="setup")return <Auth setup onReady={bootstrap}/>;if(phase==="login")return <Auth setup={false} onReady={()=>setPhase("app")}/>;
  return <div className="app"><aside><div className="logo"><i>CI</i><span>CHAT<br/><b>INSIGHT</b></span></div><nav>{NAV.map(x=><button key={x.id} className={page===x.id?"active":""} onClick={()=>setPage(x.id)}><small>{x.mark}</small>{x.label}</button>)}</nav><footer><span className="pulse"/>LOCAL ONLY<small>v0.1.1</small></footer></aside><main className="workspace">{error&&<div className="toast">{error}<button onClick={()=>setError("")}>×</button></div>}{content[page]}</main></div>;
}
