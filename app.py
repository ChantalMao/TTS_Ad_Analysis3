import streamlit as st
import pandas as pd
import google.generativeai as genai
import tempfile
import time
import os
import json
from datetime import datetime

# --- 1. 配置区域 ---
st.set_page_config(page_title="GMV MAX分析工作台", layout="wide")

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

## Data Input (你收到的 JSON 数据包含 4 个部分)
1. **分日数据**：账户整体的时间趋势。
2. **商品明细数据**：各商品的表现。
3. **素材明细数据**：原始的视频/素材粒度数据。
4. **账号表现** (系统自动计算)：这是基于素材数据聚合的**各 TikTok Account (发布账号)** 汇总表。其中“已发素材数(去重)”代表该账号下实际使用了多少个不同的 VideoId。

## 任务要求
请基于以上数据，进行全方位的诊断。在分析“账号矩阵”时，请直接使用【账号表现】的数据，点评主力账号与拖后腿账号。

## Report Output
1. 客户背景概览
2. 核心优化建议 (Action Plan)
3. 账号矩阵表现诊断 (基于“账号表现”数据)
4. 整体投放诊断 (基于“分日数据”)
5. 核心商品呈现分析
6. 素材与内容深度诊断
"""

# --- 2. Session State ---
if "sessions" not in st.session_state:
    st.session_state.sessions = {} 
if "current_task_id" not in st.session_state:
    st.session_state.current_task_id = None

# --- 3. 辅助函数 ---

def generate_task_id():
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
    clean_cols = [str(c).strip() for c in columns]
    for kw in keywords:
        for i, col in enumerate(clean_cols):
            if kw in col:
                return columns[i]
    return None

def process_excel_data(file):
    """Excel 处理核心逻辑 (指定列名版)"""
    try:
        xls = pd.ExcelFile(file)
        data_bundle = {}
        
        sheet_mapping = {
            "分时段数据": "分日数据",
            "商品-gmv max": "商品明细数据",
            "素材-gmv max": "素材明细数据"
        }
        
        material_df = None 
        
        # --- 第一步：遍历 Sheet ---
        for sheet_name in xls.sheet_names:
            clean_name = sheet_name.strip()
            for key_keyword, json_key in sheet_mapping.items():
                if key_keyword in clean_name:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    data_bundle[json_key] = df.to_dict(orient='records')
                    if json_key == "素材明细数据":
                        material_df = df
        
        # --- 第二步：计算账号表现 (指定列名 + VideoId去重) ---
        if material_df is not None:
            # 1. 使用你指定的明确列名
            acc_col = find_col(material_df.columns, ['Tiktok account'])
            cost_col = find_col(material_df.columns, ['花费'])
            gmv_col = find_col(material_df.columns, ['总收入'])
            vid_col = find_col(material_df.columns, ['VideoId'])
            
            if acc_col and cost_col and gmv_col:
                # 2. 强制转数值，防止报错
                material_df[cost_col] = pd.to_numeric(material_df[cost_col], errors='coerce').fillna(0)
                material_df[gmv_col] = pd.to_numeric(material_df[gmv_col], errors='coerce').fillna(0)
                
                # 3. 定义聚合规则
                agg_rules = {
                    cost_col: 'sum',  # 花费求和
                    gmv_col: 'sum'    # 收入求和
                }
                
                # 如果有 VideoId，增加去重计数
                if vid_col:
                    agg_rules[vid_col] = pd.Series.nunique
                
                # 4. 执行 GroupBy 聚合
                account_summary = material_df.groupby(acc_col).agg(agg_rules).reset_index()
                
                # 5. 重命名列 (让 JSON 更易读)
                rename_dict = {}
                if vid_col:
                    rename_dict[vid_col] = '已发素材数(去重)'
                account_summary.rename(columns=rename_dict, inplace=True)
                
                # 6. 计算 ROAS
                account_summary['ROAS'] = account_summary.apply(
                    lambda x: round(x[gmv_col] / x[cost_col], 2) if x[cost_col] > 0 else 0, 
                    axis=1
                )
                
                # 7. 排序 (按花费降序)
                account_summary = account_summary.sort_values(by=cost_col, ascending=False)
                data_bundle["账号表现"] = account_summary.to_dict(orient='records')
            else:
                missing = []
                if not acc_col: missing.append("Tiktok account")
                if not cost_col: missing.append("花费")
                if not gmv_col: missing.append("总收入")
                data_bundle["账号表现"] = {"Error": f"汇总失败，未找到列: {', '.join(missing)}"}
        
        # --- 第三步：转 JSON ---
        if data_bundle:
            return json.dumps(data_bundle, ensure_ascii=False, indent=2, default=str)
        else:
            return None

    except Exception as e:
        st.error(f"Excel 处理出错: {e}")
        return None

def upload_media(file, mime_type):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file.name.split('.')[-1]}") as tmp:
            tmp.write(file.getvalue())
            tmp_path = tmp.name
        g_file = genai.upload_file(tmp_path, mime_type=mime_type)
        return g_file
    except: return None

# --- 4. 侧边栏 ---
with st.sidebar:
    st.title("TTS广告分析工作台")
    st.markdown("""
    <style>
    div.stButton > button[kind="primary"] {
        background: linear-gradient(45deg, #FE6B8B 30%, #FF8E53 90%);
        border: none; color: white; font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if st.button("➕ 新建分析任务", key="new_task_main", type="primary", use_container_width=True):
        st.session_state.current_task_id = None
        st.rerun()
    
    st.divider()
    st.subheader("历史记录")
    tasks = sorted(list(st.session_state.sessions.keys()), reverse=True)
    for t_id in tasks:
        label = f"🟢 {t_id}" if t_id == st.session_state.current_task_id else f"📂 {t_id}"
        if st.button(label, key=f"btn_{t_id}", use_container_width=True):
            st.session_state.current_task_id = t_id
            st.rerun()

# --- 5. 主界面 ---
if st.session_state.current_task_id is None:
    st.title("🚀 新建分析任务")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        uploaded_excel = st.file_uploader("1. Excel 报表", type=["xlsx", "xls"])
        uploaded_image = st.file_uploader("2. 图片", type=["png", "jpg", "jpeg"])
        uploaded_video = st.file_uploader("3. 视频", type=["mp4", "mov"])
        start_btn = st.button("🚀 开始智能分析", type="primary", use_container_width=True)

    if start_btn:
        if not (uploaded_excel and uploaded_image and uploaded_video):
            st.error("⚠️ 资料不全：请同时上传 Excel、图片和视频")
        else:
            with st.status("🚀 正在启动全流程分析...", expanded=True) as status:
                
                # STEP 1: 数据处理
                status.write("📊 1/4 正在进行账号数据聚合 (VideoId去重)...")
                json_data = process_excel_data(uploaded_excel)
                
                if not json_data:
                    status.update(label="❌ Excel解析失败", state="error"); st.stop()
                
                if "账号表现" in json_data and "Error" not in json_data:
                    status.write("✅ 账号表现计算成功")
                else:
                    status.write("⚠️ 账号汇总失败 (列名不匹配)")
                time.sleep(0.5)

                # STEP 2 & 3: 素材
                status.write("🖼️ 2/4 上传图片...")
                img_file = upload_media(uploaded_image, "image/jpeg")
                status.write("🎥 3/4 上传视频...")
                vid_file = upload_media(uploaded_video, "video/mp4")
                if not (img_file and vid_file): 
                    status.update(label="❌ 素材上传失败", state="error")
                    st.stop()

                # STEP 4: 转码
                status.write("⏳ 4/4 等待 Google 转码 (90s)...")
                is_processed = False
                wait_seconds = 0
                progress_bar = st.progress(0)
                while wait_seconds < 90:
                    file_check = genai.get_file(vid_file.name)
                    if file_check.state.name == "ACTIVE":
                        is_processed = True; progress_bar.progress(100); break
                    elif file_check.state.name == "FAILED": 
                        status.update(label="❌ 转码失败", state="error")
                        st.stop()
                    time.sleep(2); wait_seconds += 2
                    progress_bar.progress(int(min(wait_seconds * 1.5, 95)))

                if not is_processed: 
                    status.update(label="❌ 转码超时", state="error")
                    st.stop()

                # STEP 5: AI
                status.write("🤖 生成报告中...")
                try:
                    model = genai.GenerativeModel("gemini-2.5-pro", system_instruction=GEM_SYSTEM_INSTRUCTION)
                    chat = model.start_chat(history=[])
                    
                    resp = chat.send_message([f"数据JSON:\n```json\n{json_data}\n```", img_file, vid_file])
                    
                    nid = generate_task_id()
                    st.session_state.sessions[nid] = {
                        "chat": chat, 
                        "history": [
                            {"role": "user", "content": "Start"}, 
                            {"role": "model", "content": resp.text}
                        ]
                    }
                    st.session_state.current_task_id = nid
                    status.update(label="✅ 完成", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

else:
    tid = st.session_state.current_task_id
    if tid not in st.session_state.sessions: 
        st.session_state.current_task_id = None
        st.rerun()
        
    sess = st.session_state.sessions[tid]
    
    st.title(f"📂 任务: {tid}")
    for msg in sess["history"]:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    
    if p := st.chat_input("输入指令..."):
        with st.chat_message("user"): st.markdown(p)
        sess["history"].append({"role": "user", "content": p})
        try:
            r = sess["chat"].send_message(p)
            with st.chat_message("model"): st.markdown(r.text)
            sess["history"].append({"role": "model", "content": r.text})
        except Exception as e: st.error(e)
