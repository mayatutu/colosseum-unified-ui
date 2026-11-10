/* Translate UI chrome only. User inputs, task text, raw logs and provider errors stay verbatim. */
const ZH = {
 'Task difficulty (1–10)':'任务难度（1–10）',
 '1 is easiest; 10 is hardest. Enter once for this task; shared by A and B.':'1 最容易，10 最难。每个任务填写一次，A/B 共用。',
 'Task difficulty is required before submitting':'请填写任务难度后再提交',
 'Task difficulty must be an integer from 1 to 10':'任务难度请填写 1 到 10 的整数',
 'Task difficulty cannot change after a dataset has been exported':'数据集已导出，不能再修改本任务的难度',
 'Initial placement reference':'任务初始摆放参考',
 'Restore the objects to match these photos before continuing.':'请对照参考图复位物品，确认后再继续。',
 'Left camera':'左侧相机','Right camera':'右侧相机',
 'Place the objects, then confirm. Left and right reference photos will be saved before the policy loads.':'摆放好物品后确认，系统会先保存左、右相机参考图，再继续任务。',
 'Both left and right cameras are required to save the initial scene':'保存初始摆放需要左、右相机均有画面，任务尚未启动',
 'The initial scene reference is missing; the trial has not started':'本任务的初始参考图缺失，本次运行尚未启动',
 'This confirmation has expired. Refresh the page.':'此确认已失效，请刷新页面',
 'Reference image could not be loaded. Refresh before continuing.':'参考图加载失败，请刷新后再继续。',
 'Statistics are read-only. This page shows the current workstation. Use All robots statistics in the top bar for the combined view.':'统计只读。本页显示当前工作站，汇总请使用顶部的“全部机器人统计”。',
 'Robots':'机器人','+ Add robot':'+ 添加机器人','Add robot':'添加机器人','Edit':'编辑','Edit robot':'编辑机器人',
 'Robot name':'机器人名称','Client workstation IP / URL':'Client 工作站 IP / 地址','e.g. Franka 1':'例如：Franka 1',
 'Default port: 8772. Use the computer running Client, not the Policy or robot controller address.':'默认端口 8772，请填写运行 Client 的电脑地址。',
 'Robot type and identity are detected automatically when its service is available.':'服务可用后自动识别机器人类型和编号。',
 'Save and check connection':'保存并检查连接','Refresh status':'刷新状态','Online':'在线','Offline':'离线',
 'All robots statistics':'全部机器人统计','Close':'关闭','Loading…':'正在加载……','Unavailable: ':'暂不可用：',
 'Beijing time. Offline workstations are marked unavailable, not counted as zero.':'按北京时间统计。离线工作站显示暂不可用，不按零条计算。',
 'Workstation unavailable or not yet running the compatible UI':'工作站离线，或尚未启动兼容的新 UI。',
 'Adding a robot does not start its services. Check the address and its UI deployment.':'添加机器人不会启动服务，请检查地址及新 UI 部署情况。',
 'Enter a robot name':'请填写机器人名称','This address is already in the robot list':'该地址已在机器人列表中',
 'Enter the workstation IP or base URL, without a path':'请填写工作站 IP 或根地址，不包含页面路径',
 'Workstation identity changed at this address':'此地址对应的工作站身份已变化，请核对地址。',
 'This workstation is already registered at another address':'这台工作站已通过另一个地址添加。',
 'Incompatible workstation service':'该工作站服务版本不兼容',
 'Translate to English':'翻译','Restore original comment':'恢复翻译前原文','Translating…':'正在翻译……',
 'Restore original task':'恢复翻译前任务','Original task':'翻译前任务','Write a task first':'请先填写任务',
 'The task changed. Close this preview and translate the latest text.':'任务已修改，请关闭预览后翻译最新内容。',
 'Translation failed. Your original task is unchanged.':'翻译暂时失败，原任务保持不变。请稍后重试。',
 'Review English translation':'确认英文译文','Original comment':'翻译前原文','English translation':'英文译文',
 'Use translation':'采用译文','Translation is empty':'译文不能为空',
 'Check the translation before using it. Your original is kept in this browser tab.':'请核对后采用译文。原文保留在当前浏览器标签页中。',
 'The comment changed. Close this preview and translate the latest text.':'总评已修改，请关闭预览后翻译最新内容。',
 'Translation backend is not configured':'尚未配置翻译后台',
 'Translation failed. Your original comment is unchanged.':'翻译暂时失败，原评语保持不变。请稍后重试。',
 '· Required':'· 必填','Describe how A and B performed. Required before submitting.':'请填写 A、B 的整体表现，提交前必填。',
 'Overall feedback is required before submitting':'请先填写综合评语再提交',
 'Optional':'可选','· Optional':'· 可选','Describe how A and B performed (optional).':'简要说明 A、B 的整体表现（可选）。',
 '✨ Polish overall comment':'✨ 整理总评','Write an overall comment first':'请先填写总评',
 'AI feedback generation is disabled in this station configuration':'此工作站配置已关闭 AI 评语生成',
 'Select evaluator':'请选择评测人员','Model not available':'模型名称尚未取得',
 'Client / Policy technical logs':'Client / Policy 技术日志',
 'Discard evaluation':'放弃评测','Reason for discarding':'放弃原因','Confirm discard':'确认放弃',
 'Close this evaluation without submitting scores. Recording files are kept.':'关闭本组评测，不提交评分。录制文件保留。',
 'A reason is required to discard':'请填写放弃原因',
 'Buffering video':'视频缓冲中','Loading video':'正在加载视频','Playback finished':'已播放结束','Playing':'播放中','Paused':'已暂停',
 'Video unavailable':'视频不可用','Playback failed':'播放失败',
 'Scene:':'场景：','Score it first':'先完成评分','is recorded but not submitted.':'已录制，尚未提交。',
 'Policy TCP reachable (protocol/model readiness is checked by the Client)':'Policy 端口可达，协议和模型就绪状态由 Client 检查',
 'Franka Policy startup check':'Franka Policy 启动检查','Policy unavailable':'Policy 服务不可达',
 'Policy was started outside this UI; left running':'此 Policy 由其他服务启动，保持运行',
 'Camera busy, try again shortly':'相机正在使用，请稍后重试','Please select or enter your name':'请选择或输入评测人员姓名',
 'Submission started. Dataset upload follows the existing Client configuration.':'已开始提交，数据集上传沿用现有 Client 配置。',
 'Submission status is unknown; no result was changed. Retry status check.':'提交状态尚未确认，未改动评分。请再次核对状态。',
 'Discard started.':'正在放弃评测。','This evaluation is closed.':'这组评测已关闭。',
 'Waiting for you':'等待确认','Loading policy':'加载策略','Returning home':'归位中','Run finished':'本次运行已结束','discarding':'正在放弃',
 '■ STOP POLICY':'■ 停止策略','Keeps the recording so far · arms return to zero · then the next policy':'保留已有录制 · 机械臂归位 · 然后进入下一个策略',
 '✓ Task done, end this run':'✓ 任务完成，结束本次运行','Policy':'策略','Step 0':'步数 0',
 'Maintenance backend is not configured':'尚未配置工作站维护后台','key saved':'已保存密钥','paste key':'粘贴密钥',
 'leave empty to keep the saved key':'留空以保留已保存的密钥','leave empty to keep using the Claude Code login':'留空以继续使用 Claude Code 登录',
 'Saved. Checking each key…':'已保存，正在验证配置……','Writing…':'正在生成……',
 'Configured credentials; see each provider status':'已读取凭据配置；验证情况见各提供商状态','Verified':'已验证',
 'Local configuration':'本机配置','Policy host file':'Policy 主机文件','Managed on the Policy host; not verified here':'由 Policy 主机 管理，此处未验证',
 'Configured; provider service URL is not available for verification':'已配置，缺少可用于验证的服务地址',
 'Robot RPC responded':'机器人 RPC 已响应','Robot RPC did not respond':'机器人 RPC 未响应',
 'No physical camera is opened by this test configuration':'此测试配置不打开真实相机',
 'Eval Station':'评测工作站','Setup':'准备','Record':'录制','Review':'回放评分','Statistics':'工作量统计',
 'Step one · once per session':'第一步 · 每次工作前准备','Get the robot':'让机器人','ready':'准备就绪',
 'Run the checks after switching the rig on. Everything should turn green.':'设备开机后执行检查，确认各项状态。',
 'Run all checks':'执行全部检查','Continue to recording →':'进入录制 →','Step two · record':'第二步 · 录制',
 'Two policies.':'两个策略。','One task.':'同一个任务。',
 'Describe the task. The Router picks two policies, A and B, and the robot tries the task once with each.':'描述任务。Router 分配 A、B 两个策略，机器人分别执行一次。',
 'Task for the robot':'机器人任务','Scene / location':'场景 / 地点','Your name':'评测人员','Max steps':'最大步数',
 'e.g. Pick up the red cup and place it on the plate':'例如：拿起红色杯子并放到盘子上','e.g. nus':'例如：实验室桌面',
 'Select or enter your name':'选择或输入姓名','Continue an interrupted evaluation':'继续中断的评测','Evaluation':'评测记录',
 '— start a new one —':'— 开始新的一组 —','Start evaluation':'开始评测',
 "You'll confirm before the robot moves. Keep the emergency stop within reach.":'机器人运动前需要确认。请确保能随时操作急停。',
 'Top camera preview':'主相机预览','Show camera':'显示画面','Top camera':'主相机','Check the scene looks right before you start.':'开始前检查场景是否正确。',
 'GPU is free':'GPU 状态','Nothing else is using the graphics card.':'检查显卡上运行的进程。','Check':'检查','Free GPU':'释放 GPU',
 'Robot connection (CAN)':'机械臂连接（CAN）','The cables from the computer to both arms.':'电脑与两侧机械臂的 CAN 连接。',
 'Bring CAN up':'恢复 CAN','Both arms respond':'双臂响应','Every motor in the left and right arm answers. Nothing moves.':'读取两侧机械臂电机响应，不执行运动。',
 'Cameras':'相机','Top camera plus the two wrist cameras.':'主相机和两个腕部相机。','Capture':'采集画面',
 'Router connection':'Router 连接','The Colosseum server that assigns policies and stores results.':'分配策略并保存评测结果的 Colosseum 服务。',
 'AI API keys (optional)':'AI API 密钥（可选）',
 'Only needed for GPT, Grok or Claude policies and AI-assisted feedback.':'仅使用 GPT、Grok、Claude 策略或 AI 辅助评语时需要配置。',
 'AI API keys':'LLM 配置','Keys for the GPT, Grok and Claude policies. Claude also writes the review feedback.':'GPT、Grok、Claude 策略配置；Claude 可辅助生成评语。',
 'API keys…':'设置…','Verify':'验证','Policy Server':'Policy 服务','Runs the policies on this computer.':'运行工作站配置的策略服务。','Start':'启动','Stop':'停止',
 'Top':'主相机','Left wrist':'左腕相机','Right wrist':'右腕相机','not captured':'未采集','not set':'未设置',
 '✓ All set. You can start recording.':'✓ 检查完成，可以开始录制。','All':'全部','To review':'待评分','Submitted':'已提交','Discarded':'已放弃',
 'needs score':'待评分','not submitted':'待提交','submitted':'已提交','discarded':'已放弃','replaced':'已被替代','interrupted':'已中断',
 'confirmation pending':'待确认','submitting':'提交中','Evaluations':'评测记录','Pick an evaluation on the left.':'从左侧选择评测记录。',
 'No evaluations yet.':'暂无评测记录。','✓ All caught up. Nothing is waiting for a score.':'✓ 暂无待评分记录。','Nothing here.':'暂无记录。',
 'Policy A':'策略 A','Policy B':'策略 B','▶ Play':'▶ 播放','Not recorded.':'尚未录制。','English or 中文':'中文或英文',
 'Your observations: what it got right, where it failed, anything unsafe…':'记录表现：完成了什么、在哪里失败、是否存在不安全行为……',
 '0 · nothing':'0 · 未完成','50 · halfway':'50 · 完成一半','100 · fully done':'100 · 全部完成',
 'Task':'任务','Compare the policies':'对比两个策略',
 'Select one option for every factor. Tie means no advantage for either policy. For Safety, select No eval when safety was not evaluated; it will be left out of the feedback.':'为每个维度选择一项。相当表示没有明显差异；未评估安全性时选择“未评估”，生成评语时将忽略该项。',
 'Speed':'速度','Smoothness':'平滑性','Safety':'安全性','Precision':'精度','Better':'更好','Slightly better':'略好','Tie':'相当','No eval':'未评估',
 'Which policy did better?':'哪个策略表现更好？','A was better':'A 更好','About the same':'基本相当','B was better':'B 更好',
 'Overall feedback':'综合评语','· English, sent to the Router':'· 英文评语，将提交到 Router',
 '✨ Write from my observations':'✨ 根据观察生成评语','Write your observations for A and B above, then click “Write from my observations”. You can edit the result.':'先填写 A、B 的观察，再生成评语；生成后可继续编辑。',
 'Discard…':'放弃…','Save draft':'保存草稿','Submit to Router':'提交到 Router','Router log':'Router 日志','Technical log':'技术日志',
 'Score this evaluation →':'为这组评测打分 →','Back to the form':'返回填写','Score both runs':'为 A、B 打分','In Review':'在回放评分页完成',
 'Recorded':'已录制','Stopped':'已停止','Waiting':'等待中','Preparing':'准备中','Cancel evaluation':'取消评测','Start robot':'启动机器人',
 'Cancel':'取消','OK':'确定','Skip and release power':'跳过并释放电机力矩','Retry return':'重试归位',
 'This is a software stop. In an emergency, press the physical stop button.':'这是软件停止。紧急情况请使用物理急停按钮。',
 'Station maintenance':'工作站维护','Uses the existing station maintenance commands. Restarting interrupts the current evaluation.':'使用工作站已有的维护命令。重启会中断当前评测。',
 'Restart Policy':'重启 Policy','Restart NUC Docker':'重启 NUC Docker 容器','Restart CAN':'恢复 CAN',
 'Service logs':'服务日志','Refresh':'刷新','Working…':'正在执行……','Completed':'已完成','Failed':'失败',
 'Local workstation · Beijing time':'本机统计 · 北京时间','Daily':'每日','evaluations':'评测工作量',
 'One A/B pair counts once after score submission is confirmed. Later dataset uploads do not change this count.':'一组 A/B 在评分提交确认成功后计 1 条；后续数据集上传不改变计数。',
 'Date':'日期','Person':'人员','Robot':'机械臂','A/B pairs':'A/B 组数','Check pending confirmations':'核对待确认提交',
 'Statistics are read-only. All people on this workstation are visible. Other workstations are not aggregated in v1.':'统计只读，可查看本机全部人员。第一版暂不汇总其他工作站。',
 'No confirmed submissions in this period.':'所选时间内暂无已确认提交。','Confirmed A/B pairs: ':'已确认 A/B 组数：',
 'Unlock settings':'解锁设置','Save and verify':'保存并验证','Show':'显示','Hide':'隐藏',
 'Keys stay on this workstation. Leave a box empty to keep its saved key.':'密钥保存在本机；留空表示保留现有密钥。',
 'Leave a box empty to keep its saved key.':'留空表示保留现有密钥。',
 'Franka credentials stay on the Policy host. Only the enabled providers can be selected here.':'Franka 凭据仍由 Policy 主机 管理；此处只选择启用的提供商。',
 'Policy host GPU':'Policy 主机 GPU','Policy workers run on the Policy host.':'模型进程运行在 Policy 主机。',
 'Robot connection (RPC)':'机器人连接（RPC）','Check the NUC robot service.':'检查 NUC 上的机器人服务。',
 'Robot service responds':'机器人服务响应','Checks RPC without creating RobotEnv.':'检查 RPC 响应，不创建 RobotEnv。',
 'Uses the existing calibrated UVC camera reader.':'使用现有已标定的 UVC 相机读取组件。',
 'Runs on the Policy host; startup checks its health.':'运行在 Policy 主机；界面启动时检查其状态。','Recover Policy workers':'恢复 Policy 模型进程',
 'Some setup checks are not green yet. Start anyway?':'部分检查尚未通过，是否仍要开始？',
 'Give both runs a score and choose which was better.':'请为 A、B 两次运行打分并选择偏好。',
 'Write a few observations for each policy first.':'请先填写策略表现的观察记录。',
 'Select one option for every factor under “Compare the policies”.':'请为每个对比维度选择一项。',
 'Replace the current feedback text?':'替换当前评语？','Submit without any feedback text?':'不填写评语，继续提交？',
 'Why discard this evaluation? (required, nothing is published)':'为什么放弃这组评测？（必填，不发布结果）',
 'Submit to the Router? Scores and feedback are submitted now. Dataset upload follows the station configuration. Continue?':'将评分和评语提交到 Router？数据集上传沿用工作站原配置。是否继续？',
 'Submit or discard this A/B pair before starting the next one.':'请提交或放弃这组 A/B 后再开始下一组。',
 'Submission confirmation is pending. Check Router status before retrying.':'提交状态待确认，请先核对 Router 状态。',
 'Submitting scores…':'正在提交评分……','Submitting scores. Dataset upload follows the station configuration.':'正在提交…',
 '✓ Submitted to the Router. It can no longer be changed here.':'✓ 已提交到 Router，不能在此修改。','Discarded. Nothing was published.':'已放弃，未发布结果。',
 'Saved on this computer.':'已在本机保存。','Draft saved. Both scores and a preference are needed to submit.':'草稿已保存；提交前需填写 A、B 评分及偏好。',
 'Lost connection to the station, reconnecting…':'与工作站连接断开，正在重连……',
 'Input needed':'需要输入','The robot is about to move':'机器人即将运动',
 'The policy is loaded. Make sure the workspace is clear and the emergency stop is within reach.':'策略已加载。请确认工作区无障碍，并可随时操作急停。',
 'Put every object back in its starting position, then click Start.':'将物体恢复到初始位置，再点击开始。',
 'Return to zero failed':'归位失败','Both runs recorded. Score them now.':'A、B 已录制完成，现在可以打分。',
 'Asking the Router for two policies…':'正在向 Router 请求两个策略……','Loading the policy. The first run of a model can take a few minutes…':'正在加载策略，首次加载模型可能需要几分钟……',
 'Starting the robot…':'正在启动机器人……','Returning the arms to zero…':'机械臂正在归位……','Saving the recording…':'正在保存录制……',
 'Ending this run…':'正在结束本次运行……','Stopping the policy and returning the arms to zero…':'正在停止策略并归位……',
 'Preparing':'准备中','Loading model':'加载模型','Starting':'启动中','Running':'运行中','Stopping':'停止中','Returning to zero':'归位中','Saving':'保存中','Between runs':'两次运行之间','Done':'完成','Error':'错误'
};
Object.assign(ZH, {
 'e.g. beside the sofa or refrigerator':'例如：沙发旁、冰箱旁',
 'Device number':'设备编号', 'Select device':'请选择设备',
 'Select the original Feishu device number':'请选择设备编号',
 'Original Feishu form':'原版飞书表单', 'Feishu confirmed: ':'飞书提交成功：',
 'Evaluation':'评测', 'Feishu status':'飞书状态', 'Retry Feishu only':'重新提交飞书',
 'Waiting for Feishu':'等待提交飞书', 'Preparing Feishu submission':'准备提交飞书',
 'Submitting to Feishu':'正在提交飞书', 'Feishu submitted':'飞书提交成功', 'Feishu failed':'飞书提交失败',
 'Feishu confirmation unknown':'飞书结果待确认', 'Feishu not enabled for this evaluation':'此评测未启用飞书',
 'Feishu reporter could not start':'飞书提交程序未能启动',
 'Feishu submission failed before confirmation. You can retry Feishu only.':'飞书提交失败，可单独重新提交飞书。',
 'Feishu confirmation is unknown. Check the table before retrying.':'未收到飞书确认，请先核对表格中是否已有此条记录。',
 'The reporting process stopped. Check the Feishu table before retrying.':'飞书提交进程已停止，请先核对表格中的提交结果。',
 'Check the original Feishu table first. Is this evaluation absent? Only continue if it has not been submitted.':'请先查看原飞书表格，确认没有这条评测记录后再重新提交。是否已确认未提交？',
 'Submit scores and feedback to the Router, then submit to the original Feishu form with both scene photos?':'确认提交评分和评语到 Router，并自动将结果及左右场景图提交到原飞书表单？',
 'Confirm and save scene':'确认保存场景',
 'Saved scene · used after refresh or restart':'已保存，刷新或重启后仍使用此场景',
 'Scene changed · confirm to save':'场景已修改，请确认保存',
 'Saving scene…':'正在保存场景……',
 'Scene must contain 1 to 4000 characters':'场景需填写 1–4000 个字符',
 'The saved scene changed. Refresh before saving again.':'其他页面已修改场景，请刷新后再保存。',
 'Robot configuration changed. Refresh before saving again.':'配置已更新，请刷新后再保存。',
 'End the current evaluation before saving the scene':'请在当前评测结束后保存场景'
});
let uiLanguage=(()=>{try{return localStorage.getItem('station-language')||'zh-CN'}catch(e){return 'zh-CN'}})();
const textSources=new WeakMap(), attributeSources=new WeakMap();
function getLanguage(){return uiLanguage}
function tr(source){
 if(uiLanguage==='en')return source;
 if(Object.hasOwn(ZH,source))return ZH[source];
 const patterns=[[/^Policy ([AB])$/,m=>'策略 '+m[1]],[/^Start Policy ([AB])$/,m=>'开始策略 '+m[1]],
 [/^Get ready for Policy ([AB])$/,m=>'准备运行策略 '+m[1]],[/^What did ([AB]) do\?$/,m=>'策略 '+m[1]+' 表现如何？'],
 [/^How much of the task did ([AB]) complete\?$/,m=>'策略 '+m[1]+' 完成了多少？'],
 [/^(\d+) of (\d+) factors selected\.$/,m=>'已选择 '+m[1]+' / '+m[2]+' 个维度。'],
 [/^Step (\d+) \/ (.+)$/,m=>'步数 '+m[1]+' / '+m[2]],
 [/^Policy Server: (.+)$/,m=>'Policy 服务：'+({running:'运行中',busy:'忙碌',stopped:'已停止'}[m[1]]||m[1])],
 [/^Still needed: (.+)$/,m=>'仍需检查：'+m[1].split(', ').map(tr).join('、')],
 [/^Policy ([AB]) finished\.$/,m=>'策略 '+m[1]+' 已结束。'],
 [/^■ Stopped by the evaluator at step (\d+)\. Recorded up to that step\.$/,m=>'■ 评测人员在第 '+m[1]+' 步停止，已保存此前记录。'],
 [/^✓ Ended by the evaluator as done at step (\d+)\.$/,m=>'✓ 评测人员在第 '+m[1]+' 步标记完成。']];
 for(const [re,fn] of patterns){const match=source.match(re);if(match)return fn(match)}
 return source;
}
function applyLanguage(){
 if(!document.body)return;
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
 while(walker.nextNode()){
  const node=walker.currentNode,parent=node.parentElement;
  if(!parent||parent.closest('script,style,textarea,pre,code,[data-user-text],#language'))continue;
  let record=textSources.get(node);
  if(!record||node.nodeValue!==record.last)record={source:node.nodeValue,last:node.nodeValue};
  const source=record.source.trim();const translated=tr(source);
  const output=record.source.replace(source,translated);
  if(node.nodeValue!==output)node.nodeValue=output;
  record.last=output;textSources.set(node,record);
 }
 document.querySelectorAll('[placeholder],[title]').forEach(el=>{
  let values=attributeSources.get(el)||{};
  for(const attr of ['placeholder','title']){const current=el.getAttribute(attr);if(current===null)continue;
   if(!values[attr]||current!==values[attr].last)values[attr]={source:current,last:current};
   const translated=tr(values[attr].source);if(current!==translated)el.setAttribute(attr,translated);values[attr].last=translated;
  }attributeSources.set(el,values);
 });
 document.documentElement.lang=uiLanguage;
}
function setLanguage(value){uiLanguage=value;try{localStorage.setItem('station-language',value)}catch(e){}
 const button=document.querySelector('#language');if(button)button.textContent=value==='zh-CN'?'English':'中文';applyLanguage()}
const nativeConfirm=window.confirm.bind(window),nativePrompt=window.prompt.bind(window);
window.confirm=text=>nativeConfirm(tr(text));window.prompt=(text,value)=>nativePrompt(tr(text),value);
document.addEventListener('DOMContentLoaded',()=>{applyLanguage();let queued=false;
 new MutationObserver(()=>{if(!queued){queued=true;queueMicrotask(()=>{queued=false;applyLanguage()})}}).observe(document.body,{childList:true,subtree:true,characterData:true});
});
