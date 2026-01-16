import streamlit as st
import pandas as pd
import google.generativeai as genai
import tempfile
import time
import os
import json # <--- 引入标准JSON库
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
你是一名专精于 TikTok GMV MAX (全域推广) 的广告优化专家。

## Data Context
你收到的数据是经过**严格清洗和聚合的 JSON 格式数据**。请将 JSON 中的数值视为**绝对事实**。
数据包含：
1. [明细] 分时段数据、商品明细、素材明细。
2. [汇总] 各发布账号的聚合表现（花费、GMV、ROAS）。

## Report Output
1. 客户背景概览
2. 核心优化建议 (Action Plan)
3. 账号矩阵表现诊断 (基于汇总数据)
4. 整体投放诊断
5. 核心商品呈现分析
6. 素材与内容深度诊断
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
            if kw in col:
                return col
    return None

def process_excel_data(file):
    """
    Excel 处理核心函数 (JSON 强化版)
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
                    
                    # 1. 保存明细 (转为字典对象)
                    data_bundle[alias] = df.to_dict(orient='records')
                    found = True
                    
                    # --- 账号汇总逻辑 ---
                    if key == "素材-gmv max":
                        account_col = find_col(df.columns, ['账号', '发布账号', 'Account', '达人'])
                        cost_col = find_col(df.columns, ['消耗', '花费', 'Cost'])
                        gmv_col = find_col(df.columns, ['GMV', 'gmv', '支付GMV', '收入', '成交'])
                        
                        if account_col and cost_col and gmv_col:
                            summary = df.groupby(account_col)[[cost_col, gmv_col]].sum().reset_index()
                            summary['ROAS'] = summary.apply(
                                lambda x: round(x[gmv_col] / x[cost_col], 2) if x[cost_col] > 0 else 0, 
                                axis=1
                            )
                            summary = summary.sort_values(by=cost_col, ascending=False)
                            data_bundle["[特别计算]各账号汇总数据"] = summary.to_dict(orient='records')
        
        if found:
            # 🔥 关键修改：使用 json.dumps 进行严格序列化
            # ensure_ascii=False: 保证中文显示为汉字，而不是 \uXXXX
            # indent=2: 格式化缩进，让结构更清晰（虽然AI不看缩进，但便于调试）
            # default=str: 遇到日期对象等无法序列化的类型，强制转为字符串
            json_str = json.dumps(data_bundle, ensure_ascii=False, indent=2, default=str)
            return json_str
        else:
            return None
            
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
    
    # CSS 美化按钮
    st.markdown("""
    <style>
    div.stButton > button[kind="primary"] {
        background: linear-gradient(45deg, #FE6B8B 30%, #FF8E53 90%);
        border: none;
        color: white;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)
    
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
    st.caption("系统将把 Excel 严格转换为 JSON 格式，并汇总账号数据")
    
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
                
                # 1. 解析 Excel (转 JSON)
                status.write("📊 1/4 正在清洗数据并转换为 JSON...")
                json_data = process_excel_data(uploaded_excel)
                
                if not json_data:
                    status.update(label="❌ Excel解析失败", state="error")
                    st.error("Excel 未找到指定 Sheet (分时段/商品/素材)。")
                    st.stop()
                
                # 检查是否包含汇总数据
                if "各账号汇总数据" in json_data:
                    status.write("✅ JSON 转换成功 (含账号聚合数据)")
                else:
                    status.write("⚠️ JSON 转换成功 (仅明细数据)")
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
                    model = genai.GenerativeModel(
                        model_name="gemini-2.5-pro", 
                        system_instruction=GEM_SYSTEM_INSTRUCTION
                    )
                    chat = model.start_chat(history=[])
                    
                    # 提示词注入
                    initial_content = [
                        f"这是处理好的投放数据(严格JSON格式)：\n```json\n{json_data}\n```\n\n请结合图片和视频进行分析。",
                        img_file,
                        vid_file
                    ]
                    
                    response = chat.send_message(initial_content)
                    
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

    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
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
