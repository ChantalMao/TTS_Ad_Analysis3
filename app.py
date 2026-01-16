import streamlit as st
import pandas as pd
import google.generativeai as genai
import tempfile
import time
import os
from datetime import datetime

# --- 1. 配置区域 ---
st.set_page_config(page_title="GMV MAX分析工作台", layout="wide")

# (A) API Key 配置
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    st.error("❌ 请在 Secrets 中配置 GEMINI_API_KEY")
    st.stop()

genai.configure(api_key=api_key)

# (B) System Instruction (Prompt)
GEM_SYSTEM_INSTRUCTION = """
# Role: TikTok Shop广告优化顾问

## Profile
你是一名专精于 TikTok GMV MAX (全域推广) 的广告优化专家。你深刻理解GMV MAX是基于“素材即定向”和“全自动托管”的广告产品。你的任务是根据数据诊断问题，并给出符合GMV MAX操作逻辑的建议。

##GMV MAX Logic Enforcement (核心知识库 - 必须严格遵守)
你必须时刻校验你的建议是否符合GMV MAX的产品特性：
1. NO Audience Targeting: GMV MAX 无法手动设置年龄、性别、兴趣或受众包。规则：严禁建议“调整受众”、“缩窄定向”或“排除某类人群”。如果转化差，请归因于素材内容未能吸引精准用户。
2. NO Manual Bidding: GMV MAX 主要是自动化出价。
规则：严禁建议“调整单个素材出价”。请建议“关停差素材”或“调整账户整体ROAS目标”。
3. Content is King: 素材和商品是GMV MAX唯一的杠杆。
规则：80%的优化建议必须聚焦在视频画面、脚本以及商品主图/标题上。

##Tone & Style Guidelines (语言风格)
1. 对象适配：请使用简单、直白、专业的语言。避免使用复杂的营销黑话（Jargon），必须使用术语时请简要解释。
2. 客观克制：严禁使用夸大、煽动性或极端的形容词（如：由“爆炸式增长”、“完美”、“极好”、“顶级”改为“显著提升”、“有效”、“表现良好”、“具有潜力”）。保持顾问的冷静与客观。
3. 结构清晰：使用表格和项目符号，确保客户一眼能看懂重点。

## Input Data Context (我将提供的资料)
1.  **广告数据-分日数据** (JSON): 包含账户整体的日期、花费、ROAS等趋势。
2.  **广告数据-商品维度数据** (JSON): 包含不同商品的ID、标题、花费(Cost)、ROAS等。
3. **广告数据-账号表现**: 包含账号维度的花费、ROAS等数据。
4.  **广告数据-素材明细数据** (JSON): VideoId, 状态, 花费, CTR, CVR等。
5.  **商品主图** (图片附件): 对应重点商品的图片。
6.  **视频素材** (视频文件): 需要优化的低绩效或待分析视频。

## Critical Execution Logic (执行逻辑 - 必须严格遵守)
**步骤一：自动背景识别 (Context Extraction)**
在开始分析前，你必须先执行以下推理，确立分析背景：
* **锁定核心商品**：读取【广告数据-商品维度数据】，找出**消耗（Cost）最高**的那一款商品。后续的“商品呈现分析”将专门针对此商品进行。
* **识别品类**：分析上述“核心商品”的标题关键词，推断其所属的垂直大类（例如：女装、3C配件、美妆个护、家居用品）。
* **识别市场**：分析提供的【视频素材】，根据视频中的**口播语言/字幕语言**，推断目标投放市场（例如：英语->欧美/东南亚英语区；泰语->泰国；越南语->越南）。

**步骤二：数据清洗与ID处理**
* **完整ID原则**：输出任何Video ID或Product ID时，必须**完整输出字符串**，严禁使用科学计数法（如1.23E+10）或省略号。

---

## Report Output (请严格按照以下结构生成报告)

### 客户背景概览 (由AI自动提取)
* **推测投放品类**：[填入根据高消耗商品标题推断的大类]
* **推测投放市场**：[填入根据视频语言推断的地区]
* **核心分析商品**：[填入高消耗商品的标题]

### 一、 核心优化建议 (Action Plan)
基于全盘分析，提供3-5个最关键、客户能立即执行的动作。
* (请使用项目符号，语言简练，优先排序高价值动作)
* ...

### 二、 整体投放诊断
**1. 趋势分析**
简要分析ROAS、花费、CVR的波动。关注是否存在“周末效应”或特定日期的异常。

**2. 关键洞察**
* 花费与ROAS的相关性分析。
* 基于数据的客观评价（避免使用“极好”等词汇）。

### 三、 核心商品呈现分析 (针对消耗TOP 1商品)
**1. 标题诊断**
* **当前标题**：[自动填入消耗最高的商品标题]
* **问题诊断**：(例如：关键词堆砌、未包含核心卖点、只有型号无品类名等)
* **优化方案**：(提供2个优化后的标题，要求包含品类大词+核心卖点，通俗易懂)

**2. 主图诊断**
* **问题诊断**：(例如：背景杂乱、商品不突出等）
* **视觉建议**：(例如：背景杂乱建议纯白底、缺乏使用场景建议增加模特图、卖点不突出建议增加贴片文案)

### 四、 素材与内容深度诊断
**1. 账号表现对比 (Account Performance)**
*基于【广告数据-账号表现】及【素材明细数据】进行统计。*
 
| TikTok Account | 发布素材数量 | 总花费 | 总收入 | 账号ROAS | 效能评价 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [Account名称] | [数量] | [金额] | [金额] | [数值] | **主力账号** (高花费高ROAS) |
| [Account名称] | [数量] | [金额] | [金额] | [数值] | **潜力账号** (低花费高ROAS) |
| [Account名称] | [数量] | [金额] | [金额] | [数值] | **亏损账号** (低ROAS) |
 
* **账号策略建议**：(基于上表，建议哪些账号应加大投入，哪些应暂停或整改)

**2. 素材绩效象限分析 (表格)**
基于【素材明细数据】，将素材分类。
* **ID显示注意**：Video ID必须完整显示。

| 素材类型 | 定义标准 | 典型Video ID (完整) | 建议操作 |
| :--- | :--- | :--- | :--- |
| 明星素材 | 高花费/高ROAS | ... | 保持预算/尝试拓量 |
| 问题素材 | 高花费/低ROAS | ... | 降价/暂停/优化前3秒 |
| 潜力素材 | 低花费/高ROAS | ... | 逐步提价测试 |
| 待淘汰素材 | 低花费/低ROAS | ... | 立即关停 |

**3. 低绩效视频深度归因**
针对提供的具体视频文件进行分析。
*重点分析为何该视频投放效果不佳。*

| 时间点 | 画面内容 | 文案/旁白 | 问题分析 (客观描述) | 优化建议 (可执行) |
| :--- | :--- | :--- | :--- | :--- |
| 0-3秒 | ... | ... | ... | ... |
| 中段 | ... | ... | ... | ... |
| 结尾 | ... | ... | ... | ... |

* **失败核心归因**：用一句话总结该视频转化差的原因（如：完播率低导致无转化，或引导下单不明确）。

### 五、 爆款脚本参考 (SME适用版)
**1. 市场洞察**
基于你推断的[品类]和[市场]，简述该地区用户的基本偏好。

**2. 简易爆款公式**
为客户提供一个低成本、易上手的拍摄脚本模板。

| 时间 | 阶段 | 画面建议 (低成本方案) | 文案示例 |
| :--- | :--- | :--- | :--- |
| 0-3s | 黄金开头 | ... | ... |
| 3-10s | 痛点/展示 | ... | ... |
| 10s+ | 引导下单 | ... | ... |
"""

# --- 2. Session State 初始化 ---
if "sessions" not in st.session_state:
    st.session_state.sessions = {} 
if "current_task_id" not in st.session_state:
    st.session_state.current_task_id = None

# --- 3. 辅助函数 ---

def generate_task_id():
    """生成唯一任务ID: MMDD-NN"""
    today_str = datetime.now().strftime('%m%d')
    count = 1
    for task_id in st.session_state.sessions.keys():
        if task_id.startswith(today_str):
            try:
                suffix = int(task_id.split('-')[1])
                if suffix >= count:
                    count = suffix + 1
            except:
                pass
    return f"{today_str}-{count:02d}"

def find_col(columns, keywords):
    """辅助函数：模糊查找列名"""
    for col in columns:
        for kw in keywords:
            if kw in col: # 只要包含关键词就算匹配 (比如 "消耗(元)" 匹配 "消耗")
                return col
    return None

def process_excel_data(file):
    """
    Excel 处理核心函数
    功能：
    1. 读取所有 Sheet 转 JSON
    2. 特别针对 '素材-gmv max' 进行账号维度的 GroupBy 汇总
    """
    try:
        xls = pd.ExcelFile(file)
        data_bundle = {}
        
        target_sheets = {
            "分时段数据": "分时段表现",
            "商品-gmv max": "商品GMV明细",
            "素材-gmv max": "素材GMV明细"
        }
        
        found = False
        for sheet_name in xls.sheet_names:
            clean_name = sheet_name.strip()
            for key, alias in target_sheets.items():
                if key in clean_name:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    
                    # 1. 保存原始明细数据
                    data_bundle[alias] = df.to_dict(orient='records')
                    found = True
                    
                    # --- 新增逻辑：如果是素材表，进行账号汇总 ---
                    if key == "素材-gmv max":
                        # 1. 模糊匹配列名
                        account_col = find_col(df.columns, ['账号', '发布账号', 'Account', '达人'])
                        cost_col = find_col(df.columns, ['消耗', '花费', 'Cost'])
                        gmv_col = find_col(df.columns, ['GMV', 'gmv', '支付GMV', '收入', '成交'])
                        
                        if account_col and cost_col and gmv_col:
                            # 2. 聚合计算
                            summary = df.groupby(account_col)[[cost_col, gmv_col]].sum().reset_index()
                            
                            # 3. 计算 ROAS (避免除以0)
                            summary['ROAS'] = summary.apply(
                                lambda x: round(x[gmv_col] / x[cost_col], 2) if x[cost_col] > 0 else 0, 
                                axis=1
                            )
                            
                            # 4. 排序 (按消耗降序)
                            summary = summary.sort_values(by=cost_col, ascending=False)
                            
                            # 5. 存入数据包
                            data_bundle["[特别计算]各账号汇总数据"] = summary.to_dict(orient='records')
                            
        return str(data_bundle) if found else None
    except Exception as e:
        st.error(f"Excel 处理出错: {e}")
        return None

def upload_media(file, mime_type):
    """上传文件到 Gemini"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file.name.split('.')[-1]}") as tmp:
            tmp.write(file.getvalue())
            tmp_path = tmp.name
        g_file = genai.upload_file(tmp_path, mime_type=mime_type)
        return g_file
    except: return None

# --- 4. 侧边栏：任务导航 ---
with st.sidebar:
    st.title("TTS广告分析工作台")
    
    if st.button("➕ 新建分析任务", key="new_task_main", type="primary", use_container_width=True):
        st.session_state.current_task_id = None
        st.rerun()
    
    st.divider()
    st.subheader("历史记录")
    
    tasks = sorted(list(st.session_state.sessions.keys()), reverse=True)
    if not tasks:
        st.caption("暂无历史任务")
    
    for t_id in tasks:
        label = f"📂 {t_id}"
        if t_id == st.session_state.current_task_id:
            label = f"🟢 {t_id} (当前)"
        if st.button(label, key=f"btn_{t_id}", use_container_width=True):
            st.session_state.current_task_id = t_id
            st.rerun()

# --- 5. 主界面逻辑 ---

# SCENE 1: 新建任务界面
if st.session_state.current_task_id is None:
    st.title("🚀 新建分析任务")
    st.caption("系统将自动对【发布账号】维度进行汇总计算，并提交给 AI")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        uploaded_excel = st.file_uploader("1. 周期性复盘报告 (Excel)", type=["xlsx", "xls"])
        uploaded_image = st.file_uploader("2. 核心商品主图", type=["png", "jpg", "jpeg", "webp"])
        uploaded_video = st.file_uploader("3. 低绩效视频素材", type=["mp4", "mov", "avi"])
        
        start_btn = st.button("🚀 开始智能分析", type="primary", use_container_width=True)

    if start_btn:
        if not (uploaded_excel and uploaded_image and uploaded_video):
            st.error("⚠️ 资料不全！必须上传：Excel、图片和视频。")
        else:
            with st.status("🚀 正在启动全流程分析...", expanded=True) as status:
                
                # 1. 解析 Excel
                status.write("📊 1/4 正在解析 Excel 并汇总账号数据...")
                json_data = process_excel_data(uploaded_excel)
                
                if not json_data:
                    status.update(label="❌ Excel解析失败", state="error")
                    st.error("Excel 未找到指定 Sheet (分时段/商品/素材)。")
                    st.stop()
                
                if "[特别计算]各账号汇总数据" in json_data:
                    status.write("✅ 已成功提取并汇总各账号 ROAS 数据")
                else:
                    status.write("⚠️ 未检测到账号列，跳过账号汇总，仅分析明细")
                time.sleep(0.5)

                # 2. 上传图片
                status.write("🖼️ 2/4 正在上传图片...")
                img_file = upload_media(uploaded_image, "image/jpeg")
                if not img_file:
                    status.update(label="❌ 图片上传失败", state="error")
                    st.stop()

                # 3. 上传视频
                status.write("🎥 3/4 正在上传视频 (大文件耗时较长)...")
                vid_file = upload_media(uploaded_video, "video/mp4")
                if not vid_file:
                    status.update(label="❌ 视频上传失败", state="error")
                    st.stop()
                
                # 4. 等待视频转码
                status.write("⏳ 4/4 等待 Google 视频转码 (最长 90s)...")
                is_processed = False
                wait_seconds = 0
                progress_bar = st.progress(0)
                
                while wait_seconds < 90:
                    file_check = genai.get_file(vid_file.name)
                    if file_check.state.name == "ACTIVE":
                        is_processed = True
                        progress_bar.progress(100)
                        break
                    elif file_check.state.name == "FAILED":
                        status.update(label="❌ 视频转码失败", state="error")
                        st.stop()
                    
                    time.sleep(2)
                    wait_seconds += 2
                    progress_bar.progress(int(min(wait_seconds * 1.5, 95)))
                    status.write(f"⏳ Google 转码中... {wait_seconds}s")

                if not is_processed:
                    status.update(label="❌ 视频处理超时", state="error")
                    st.error("视频处理超时，请压缩视频大小。")
                    st.stop()

                # 5. 呼叫 Gemini
                status.write("🤖 素材就绪，正在生成深度分析报告...")
                try:
                    # 使用 1.5-pro 以获得更好效果，如果没权限请改回 1.5-flash
                    model = genai.GenerativeModel(
                        model_name="gemini-2.5-pro", 
                        system_instruction=GEM_SYSTEM_INSTRUCTION
                    )
                    chat = model.start_chat(history=[])
                    
                    initial_content = [
                        f"这是投放数据(JSON)：\n{json_data}\n\n请结合图片和视频进行分析。",
                        img_file,
                        vid_file
                    ]
                    
                    response = chat.send_message(initial_content)
                    
                    # 创建任务
                    new_task_id = generate_task_id()
                    
                    st.session_state.sessions[new_task_id] = {
                        "chat": chat,
                        "history": [
                            {"role": "user", "content": "【系统指令】分析数据与素材"},
                            {"role": "model", "content": response.text}
                        ]
                    }
                    
                    st.session_state.current_task_id = new_task_id
                    status.update(label="✅ 分析完成！正在跳转...", state="complete")
                    time.sleep(1)
                    st.rerun()
                    
                except Exception as e:
                    status.update(label="❌ AI 分析出错", state="error")
                    st.error(f"API 错误: {e}")

# SCENE 2: 历史任务详情页
else:
    task_id = st.session_state.current_task_id
    
    if task_id not in st.session_state.sessions:
        st.session_state.current_task_id = None
        st.rerun()
        
    session_data = st.session_state.sessions[task_id]
    chat_session = session_data["chat"]
    history = session_data["history"]
    
    st.title(f"📂 任务详情: {task_id}")

    # 显示对话历史
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # 对话输入
    if prompt := st.chat_input("输入修正指令或后续问题..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        history.append({"role": "user", "content": prompt})
        
        try:
            with st.spinner("Gemini 正在思考..."):
                response = chat_session.send_message(prompt)
                with st.chat_message("model"):
                    st.markdown(response.text)
                history.append({"role": "model", "content": response.text})
                st.session_state.sessions[task_id]["history"] = history
        except Exception as e:
            st.error(f"回复出错: {e}")
