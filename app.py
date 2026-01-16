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
4. **账号表现** (系统自动计算)：这是基于素材数据聚合的**各 TikTok Account (发布账号)** 汇总表。

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
    """Excel 处理核心逻辑 (Pivot Table 版)"""
    try:
        xls = pd.ExcelFile(file)
        data_bundle = {}
        
        sheet_mapping = {
            "分时段数据": "分日数据",
            "商品-gmv max": "商品明细数据",
