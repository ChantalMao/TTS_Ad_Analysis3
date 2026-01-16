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
        
        # --- 第二步：Pivot Table 计算账号表现 ---
        if material_df is not None:
            acc_col = find_col(material_df.columns, ['账号', '发布账号', 'Account', '达人', 'Handle'])
            cost_col = find_col(material_df.columns, ['消耗', '花费', 'Cost', 'Spend'])
            gmv_col = find_col(material_df.columns, ['GMV', 'gmv', '支付GMV', '收入', '成交'])
            
            if acc_col and cost_col and gmv_col:
                # 强制转数值，防止报错
                material_df[cost_col] = pd.to_numeric(material_df[cost_col], errors='coerce').fillna(0)
                material_df[gmv_col] = pd.to_numeric(material_df[gmv_col], errors='coerce').fillna(0)
                
                # 透视表聚合
                account_summary = pd.pivot_table(
                    material_df,
                    index=acc_col,
                    values=[cost_col, gmv_col],
                    aggfunc='sum',
                    fill_value=0
                ).reset_index()
                
                # 计算 ROAS
                account_summary['ROAS'] = account_summary.apply(
                    lambda x: round(x[gmv_col] / x[cost_col], 2) if x[cost_col] > 0 else 0, 
                    axis=1
                )
                
                # 排序
                account_summary = account_summary.sort_values(by=cost_col, ascending=False)
                data_bundle["账号表现"] = account_summary.to_dict(orient='records')
            else:
                data_bundle["账号表现"] = {"Error": "汇总失败：未找到账号/消耗/GMV列"}
        
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
        g_file = genai.upload_file(tmp_path, mime_
