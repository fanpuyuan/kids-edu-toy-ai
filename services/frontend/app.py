import streamlit as st
import asyncio
import websockets
import json
import base64
import os
import requests
from pathlib import Path
from st_audiorec import st_audiorec

# --- 1. SUPER ROBUST INITIALIZATION ---
def init_state():
    if "current_config" not in st.session_state:
        default_cfg = {
            "llm_env": "cloud",
            "llm_api_key": os.getenv("DEFAULT_CLOUD_API_KEY", ""),
            "llm_model": "deepseek-chat",
            "embedding_provider": "dashscope",
            "embedding_api_key": os.getenv("DEFAULT_CLOUD_API_KEY", ""),
            "tts_voice": "zh-CN-XiaoxiaoNeural",
            "tts_rate": "+0%"
        }
        try:
            res = requests.get(f"{os.getenv('GATEWAY_URL', 'http://gateway:8000')}/config", timeout=2.0)
            if res.status_code == 200:
                saved_cfg = res.json().get("configs", {})
                default_cfg.update(saved_cfg)
        except Exception as e:
            pass # Use defaults if gateway is unreachable
            
        st.session_state["current_config"] = default_cfg
        
    if "available_models" not in st.session_state:
        st.session_state["available_models"] = []

init_state()

# Helper to avoid dot notation crash
def get_config_val(key, default=""):
    return st.session_state["current_config"].get(key, default)

st.set_page_config(page_title="🧸 智能伴读玩具控制台", layout="centered")

# Constants
GATEWAY_URL = "http://gateway:8000"
BACKEND_URL = os.getenv("BACKEND_URL", "ws://localhost:8080/ws")

st.title("🧸 智能伴读玩具 Demo界面")
st.markdown("模拟硬件玩具终端：录音 -> 发送 -> 接收文字与语音流")

# --- 2. Sidebar: Configuration & Management ---
with st.sidebar:
    st.header("⚙️ 全局配置")
    
    with st.expander("🛠️ 模型与引擎管理", expanded=True):
        # A. Ollama Status
        try:
            status_res = requests.get(f"{GATEWAY_URL}/ollama_status", timeout=2)
            if status_res.status_code == 200:
                models = [m["name"] for m in status_res.json().get("models", [])]
                st.session_state["available_models"] = models
                st.write(f"**Ollama 已下载:** \n" + ", ".join(models) if models else "无")
            else:
                st.error("无法获取 Ollama 状态")
        except:
            st.warning("⏳ 正在载入/等待网关...")

        st.divider()
        
        # B. Embedding Provider
        st.subheader("向量引擎 (Embedding)")
        current_p = get_config_val("embedding_provider", "local")
        emb_provider = st.radio(
            "选择引擎",
            ["local", "dashscope"],
            index=0 if current_p == "local" else 1,
            help="Local: 本地 BGE (免费), DashScope: 阿里云 (更精准)"
        )
        st.session_state["current_config"]["embedding_provider"] = emb_provider
        
        # C. Dynamic Embedding API Key
        current_ekey = get_config_val("embedding_api_key", "")
        if emb_provider == "dashscope":
            emb_api_key = st.text_input("DashScope API Key", value=current_ekey, type="password")
            st.session_state["current_config"]["embedding_api_key"] = emb_api_key
        else:
            st.session_state["current_config"]["embedding_api_key"] = ""

    st.divider()
    
    # D. LLM Brain Config
    st.subheader("🧠 大脑配置 (LLM)")
    llm_env_flag = st.radio("生成环境", ["Local (Ollama)", "Cloud (API)"], 
                            index=0 if get_config_val("llm_env") == "local" else 1)
    
    ll_key = st.text_input("云端 API Key", value=get_config_val("llm_api_key"), type="password") if llm_env_flag == "Cloud (API)" else ""
    
    if llm_env_flag == "Cloud (API)":
        model_opts = ["deepseek-chat", "glm-4"]
    else:
        # Dynamically use downloaded models, fallback if none found
        avail = st.session_state.get("available_models", [])
        model_opts = avail if len(avail) > 0 else ["qwen3.5:0.8b", "llama3.1:8b"]
    
    sel_model = st.selectbox("选择大模型", model_opts, index=0)
    ll_temp = st.slider("脑电波强度 (Temp)", 0.0, 1.2, 0.7)

    st.divider()
    
    # E. Voice Config
    # E. Voice Config
    st.subheader("🔊 声音配置 (TTS)")
    tts_e = st.radio("TTS 引擎", ["Edge-TTS (免费)", "CosyVoice (声音克隆)"], 
                     index=0 if get_config_val("tts_engine", "edge-tts") == "edge-tts" else 1)
                     
    cosy_api_key = ""
    if tts_e == "CosyVoice (声音克隆)":
        cosy_api_key = st.text_input("DashScope / CosyVoice API Key", value=get_config_val("cosyvoice_api_key", ""), type="password")
        
        # 阿里云 CosyVoice 专属音色列表
        cosy_voices = [
            "longxiaochun (龙小淳 - 默认女声)",
            "longxiaoxia (龙小夏 - 活泼女童)",
            "longxiaocheng (龙小诚 - 稳重男声)"
        ]
        # 追加从本地配置里读出的已克隆的用户专属声音
        saved_custom_voice = get_config_val("cosyvoice_custom_id", "")
        if saved_custom_voice:
            cosy_voices.append(f"{saved_custom_voice} (爸爸/妈妈克隆音)")
            
        default_idx = 0
        saved_voice = get_config_val("tts_voice", "")
        for i, v in enumerate(cosy_voices):
            if saved_voice in v:
                default_idx = i
                break
                
        tts_v_raw = st.selectbox("音色 (CosyVoice)", cosy_voices, index=default_idx)
        tts_v = tts_v_raw.split(" (")[0]
        
        # --- 声音克隆录制区域 ---
        with st.expander("🎙️ 克隆我的声音 (需 3-10 秒清晰录音)"):
            if not cosy_api_key:
                st.warning("请先在上方填写 DashScope API Key")
            else:
                clone_audio = st.file_uploader("上传清晰讲话录音 (.wav / .mp3)", type=["wav", "mp3"])
                if st.button("开始生成克隆专属音色"):
                    if clone_audio:
                        with st.spinner("正在上传至阿里云进行 Zero-shot 声音克隆..."):
                            try:
                                # Send to TTS service directly or via gateway for enrollment
                                files = {"audio": (clone_audio.name, clone_audio.getvalue(), clone_audio.type)}
                                data = {"api_key": cosy_api_key}
                                res = requests.post(f"{GATEWAY_URL}/clone_voice", files=files, data=data, timeout=30.0)
                                
                                if res.status_code == 200:
                                    result = res.json()
                                    if result.get("status") == "success":
                                        new_voice_id = result.get("voice_id")
                                        st.success(f"克隆成功！已获得专属 Voice ID: {new_voice_id}")
                                        # Save to session instantly so it updates the selectbox on next refresh
                                        st.session_state["current_config"]["cosyvoice_custom_id"] = new_voice_id
                                    else:
                                        st.error(f"克隆失败: {result.get('message')}")
                                else:
                                    st.error(f"服务器错误: {res.text}")
                            except Exception as e:
                                st.error(f"网络请求失败: {e}")
                    else:
                        st.warning("请先上传音频文件。")
        
    else:
        # 微软 Edge-TTS 专属音色列表
        edge_voices = [
            "zh-CN-XiaoxiaoNeural (晓晓 - 女萌)", 
            "zh-CN-YunxiNeural (云希 - 男活泼)", 
            "zh-CN-YunjianNeural (云健 - 男稳重)",
            "zh-HK-HiuMaanNeural (晓曼 - 粤语女)"
        ]
        default_idx = 0
        saved_voice = get_config_val("tts_voice", "zh-CN-XiaoxiaoNeural")
        for i, v in enumerate(edge_voices):
            if saved_voice in v:
                default_idx = i
                break
                
        tts_v_raw = st.selectbox("音色 (Edge-TTS)", edge_voices, index=default_idx)
        tts_v = tts_v_raw.split(" (")[0]
        
    tts_r = st.select_slider("语速", options=["-50%", "-20%", "+0%", "+20%", "+50%"], value="+0%")
    
    c_age = st.number_input("儿童年龄", 1, 12, 5)

# Sync all to session state
st.session_state["current_config"].update({
    "llm_env": "cloud" if llm_env_flag == "Cloud (API)" else "local",
    "llm_api_key": ll_key,
    "llm_model": sel_model,
    "llm_temp": ll_temp,
    "tts_engine": "cosyvoice" if tts_e == "CosyVoice (声音克隆)" else "edge-tts",
    "cosyvoice_api_key": cosy_api_key,
    "tts_voice": tts_v,
    "tts_rate": tts_r
})
current_config = st.session_state["current_config"]

st.divider()
if st.sidebar.button("💾 保存设置为系统默认", use_container_width=True):
    try:
        res = requests.post(f"{GATEWAY_URL}/config", json=current_config, timeout=5.0)
        if res.status_code == 200:
            st.sidebar.success("全局配置已持久化！")
        else:
            st.sidebar.error("配置保存失败")
    except Exception as e:
        st.sidebar.error(f"连接失败: {e}")

# --- 3. Main Interface ---
tabs = st.tabs(["🎤 语音助手", "⌨️ 文字聊天", "📚 知识库管理", "👨‍👩‍👧 记忆档案"])

def get_payload_with_config(action, data):
    return {
        "action": action,
        "data": data,
        "config": current_config
    }

async def ws_chat(payload):
    text_area = st.empty()
    full_text = ""
    try:
        async with websockets.connect(BACKEND_URL) as ws:
            await ws.send(json.dumps(payload))
            while True:
                resp = json.loads(await ws.recv())
                if resp["type"] == "text_chunk":
                    full_text += resp["data"]["text"]
                    text_area.markdown(f"**AI:** {full_text}")
                elif resp["type"] == "audio_chunk":
                    st.audio(base64.b64decode(resp["data"]["audio"]), format="audio/mp3", autoplay=True)
                elif resp["type"] == "response_complete":
                    st.success("对话结束")
                    break
    except Exception as e:
        st.error(f"连接失败: {e}")

with tabs[0]:
    st.subheader("🎤 语音交流")
    audio_data = st_audiorec()
    if audio_data:
        if st.button("🚀 发送语音"):
            p = get_payload_with_config("audio", {"audio": base64.b64encode(audio_data).decode(), "context": {"child_age": c_age}})
            asyncio.run(ws_chat(p))

with tabs[1]:
    st.subheader("⌨️ 文字对话")
    u_text = st.text_area("输入你想说的话...", height=100)
    if st.button("🚀 发送文本"):
        if u_text.strip():
            p = get_payload_with_config("chat", {"text": u_text, "context": {"child_age": c_age}})
            asyncio.run(ws_chat(p))

with tabs[2]:
    st.subheader("📚 知识库管理")
    provider = current_config["embedding_provider"]
    api_key = current_config["embedding_api_key"]
    
    # List files
    try:
        r = requests.get(f"{GATEWAY_URL}/list_docs", params={"embedding_provider": provider}, timeout=5.0)
        docs_data = r.json()
        docs = docs_data.get("documents", []) if r.status_code == 200 else []
        if r.status_code != 200:
            st.error(f"获取文档列表失败: {r.status_code}")
    except Exception as e:
        st.error(f"连接失败: {e}")
        docs = []
    
    st.write(f"当前引擎: **{provider}**")
    if not docs:
        st.info("该引擎下尚无文件。")
    for d in docs:
        cols = st.columns([5, 3, 2])
        cols[0].text(d["filename"])
        cols[1].text(d["upload_time"][:16])
        if cols[2].button("删除", key=f"del_{d['doc_id']}"):
            requests.post(f"{GATEWAY_URL}/delete_doc", json={"doc_id": d["doc_id"], "embedding_provider": provider, "embedding_api_key": api_key})
            st.rerun()

    st.divider()
    up_file = st.file_uploader("上传知识 (Txt/Md/Pdf/Docx)", type=["txt", "md", "pdf", "docx"])
    c1, c2 = st.columns(2)
    if c1.button("🚀 开始解析上传"):
        if up_file:
            with st.spinner("正在解析并同步到向量引擎..."):
                try:
                    res = requests.post(f"{GATEWAY_URL}/upload_doc", 
                                        files={"file": (up_file.name, up_file.getvalue(), up_file.type)}, 
                                        data={"embedding_provider": provider, "embedding_api_key": api_key},
                                        timeout=120.0)
                    if res.status_code == 200:
                        st.success("上传并解析成功！")
                        st.rerun()
                    else:
                        st.error(f"上传失败 ({res.status_code}): {res.text}")
                except Exception as e:
                    st.error(f"连接网关失败: {e}")
    if c2.button("🔥 清空当前引擎库"):
        with st.spinner("清理中..."):
            try:
                res = requests.post(f"{GATEWAY_URL}/clear_docs", 
                                    params={"embedding_provider": provider, "embedding_api_key": api_key},
                                    timeout=10.0)
                if res.status_code == 200:
                    st.success("已清空！")
                    st.rerun()
                else:
                    st.error(f"清空失败: {res.text}")
            except Exception as e:
                st.error(f"连接库失败: {e}")

with tabs[3]:
    st.subheader("👨‍👩‍👧 家庭记忆")
    m_map = {"核心设定 (SYSTEM)": "SYSTEM", "家庭档案 (FAMILY)": "FAMILY", "近期碎片 (SNAPSHOT)": "SNAPSHOT"}
    m_label = st.selectbox("选择记忆分类", list(m_map.keys()))
    m_id = m_map[m_label]
    try:
        m_content = requests.get(f"{GATEWAY_URL}/memory/{m_id}").json().get("content", "")
    except:
        m_content = ""
    new_m = st.text_area("查看/编辑", value=m_content, height=250)
    if st.button("💾 保存记忆"):
        requests.post(f"{GATEWAY_URL}/memory/update", json={"layer": m_id, "content": new_m})
        st.success("保存成功！")
