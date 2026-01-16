import streamlit as st
import pandas as pd
import google.generativeai as genai
import tempfile
import time
import os
from datetime import datetime

# --- 1. 配置区域 ---
st.set_page_config(page_title="GMV 智能分析工作台", layout="wide")

# (A) API Key 配置
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    st.error("❌ 请在 Secrets 中配置 GEMINI_API_KEY")
    st.stop()

genai.configure(api_key=api_key)

# (B) System Instruction (Prompt)
GEM_SYSTEM_INSTRUCTION = """
你是一位资深的电商广告投放分析专家。
你的任务是基于用户上传的“完整数据包”（Excel数据 + 封面图 + 视频）进行深度归因分析。

【分析逻辑】
1. **数据诊断**：根据 Excel (JSON) 数据，指出消耗、GMV、ROI 的关键表现和波动。
2. **素材归因**：结合视频内容和封面图，分析素材与数据的关系。
3. **结论与建议**：给出明确的优化动作。

输出风格：专业、直接、行动导向。
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

def process_excel_data(file):
    """Excel 转 JSON"""
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
                    data_bundle[alias] = df.to_dict(orient='records')
                    found = True
        return str(data_bundle) if found else None
    except: return None

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
    st.title("🗂️ 工作台")
    
    # 新建任务按钮
    if st.button("➕ 新建分析任务", key="new_task_main", type="primary", use_container_width=True):
        st.session_state.current_task_id = None
        st.rerun()
    
    st.divider()
    st.subheader("历史记录")
    
    # 获取任务列表并排序
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

# SCENE 1: 新建任务界面 (如果当前ID为空)
if st.session_state.current_task_id is None:
    st.title("🚀 新建分析任务")
    st.caption("上传素材后，系统将自动创建新会话")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        uploaded_excel = st.file_uploader("1. Excel 报表 (必填)", type=["xlsx", "xls"])
        uploaded_image = st.file_uploader("2. 广告封面图 (必填)", type=["png", "jpg", "jpeg", "webp"])
        uploaded_video = st.file_uploader("3. 广告视频 (必填)", type=["mp4", "mov", "avi"])

    with col2:
        st.info("💡 提示：")
        st.markdown("""
        - 点击 **开始分析** 后，系统会自动生成任务 ID (如 0116-01)。
        - 图片和视频将**不再预览**，直接在后台处理。
        - 分析过程可能需要 30-60秒，请耐心等待。
        """)
        
        start_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)

    if start_btn:
        if not (uploaded_excel and uploaded_image and uploaded_video):
            st.error("⚠️ 资料不全！请必须同时上传：Excel、图片 和 视频。")
        else:
            with st.status("🚀 正在启动任务...", expanded=True) as status:
                
                # 1. 解析 Excel
                status.write("📊 1/4 正在解析 Excel 数据...")
                json_data = process_excel_data(uploaded_excel)
                if not json_data:
                    status.update(label="❌ Excel 解析失败", state="error")
                    st.error("Excel 未找到指定 Sheet。")
                    st.stop()
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
                
                # 4. 等待视频转码 (带超时)
                status.write("⏳ 4/4 等待 Google 视频转码 (最长 60s)...")
                is_processed = False
                wait_seconds = 0
                progress_bar = st.progress(0)
                
                while wait_seconds < 60:
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
                    
                    # ⚠️ 修复点：强制转换为整数 int()
                    progress_value = int(min(wait_seconds * 1.5, 95))
                    progress_bar.progress(progress_value)
                    
                    status.write(f"⏳ Google 转码中... {wait_seconds}s")

                if not is_processed:
                    status.update(label="❌ 视频处理超时", state="error")
                    st.error("视频处理超时，请压缩视频大小。")
                    st.stop()

                # 5. 呼叫 Gemini
                status.write("🤖 素材就绪，正在生成分析报告...")
                try:
                    model = genai.GenerativeModel(
                        model_name="gemini-1.5-flash",
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

# SCENE 2: 历史任务详情页 (Chat 界面)
else:
    task_id = st.session_state.current_task_id
    
    if task_id not in st.session_state.sessions:
        st.session_state.current_task_id = None
        st.rerun()
        
    session_data = st.session_state.sessions[task_id]
    chat_session = session_data["chat"]
    history = session_data["history"]
    
    st.title(f"📂 任务详情: {task_id}")
    
    # 显示历史
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