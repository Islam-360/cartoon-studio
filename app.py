import os
import json
import time
import shutil
import subprocess
from pathlib import Path
from typing import List
import requests
import streamlit as st
from pydantic import BaseModel
from google import genai
from google.genai import types
import fal_client

BASE_DIR = Path("studio_workspace")
BASE_DIR.mkdir(exist_ok=True)
CHAR_FILE = BASE_DIR / "characters.json"

st.set_page_config(page_title="استوديو يوميات الكرتون", page_icon="🎬", layout="wide")

class SceneItem(BaseModel):
    scene_number: int
    speaker: str
    dialogue: str
    emotion_tag: str
    image_prompt: str
    motion_prompt: str

class EpisodePlan(BaseModel):
    episode_title: str
    viral_titles: List[str]
    post_description: str
    hashtags: List[str]
    scenes: List[SceneItem]

def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

def download_file(url: str, dest: Path) -> Path:
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest

def ensure_min_audio_duration(audio_path: Path, min_sec: float = 2.2) -> Path:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True
    )
    try:
        dur = float(probe.stdout.strip())
    except ValueError:
        dur = min_sec
    if dur >= min_sec:
        return audio_path
    padded_path = audio_path.with_name(f"padded_{audio_path.name}")
    pad_amount = round(min_sec - dur + 0.1, 2)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio_path), "-af", f"apad=pad_dur={pad_amount}", str(padded_path)],
        check=True, capture_output=True
    )
    return padded_path

def merge_video_and_audio(video_path: Path, audio_path: Path, out_path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path), "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out_path)],
        check=True, capture_output=True
    )

def concat_episode_clips(clip_paths: List[Path], final_output: Path):
    normalized = []
    for i, clip in enumerate(clip_paths):
        norm = clip.with_name(f"norm_{i}_{clip.name}")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(clip),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", str(norm)
            ],
            check=True, capture_output=True
        )
        normalized.append(norm)
    list_file = final_output.with_suffix(".txt")
    list_file.write_text("\n".join([f"file '{p.resolve()}'" for p in normalized]), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(final_output)],
        check=True, capture_output=True
    )

def load_characters():
    if CHAR_FILE.exists():
        return json.loads(CHAR_FILE.read_text(encoding="utf-8"))
    return {
        "char1_name": "خسة",
        "char1_desc": "A funny 3D Pixar-style cartoon Egyptian young man in his 20s, wearing a trendy casual hoodie and jeans, expressive big eyes, witty cheerful smile, clean 3D animation render",
        "char1_voice": "Adam",
        "char1_url": "",
        "char2_name": "لفتة",
        "char2_desc": "A charming funny 3D Pixar-style cartoon Syrian young woman in her 20s, wearing a stylish modern casual jacket and jeans, expressive bright eyes, friendly witty smile, clean 3D animation render",
        "char2_voice": "Rachel",
        "char2_url": "",
    }

def save_characters(data: dict):
    CHAR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

with st.sidebar:
    st.header("🔑 إعدادات المحرك")
    gemini_key = st.text_input("Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    fal_key = st.text_input("fal.ai API Key", type="password", value=os.environ.get("FAL_KEY", ""))
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key
    if fal_key:
        os.environ["FAL_KEY"] = fal_key
    st.divider()
    if check_ffmpeg():
        st.success("✅ FFmpeg جاهز للمونتاج")
    else:
        st.error("⚠️ FFmpeg غير مثبت")

st.title("🎬 استوديو يوميات الكرتون الخاص")
st.caption("أفكار + اسكربت بلهجات متعددة + ثبات الشخصيات + أصوات + Lip-Sync + تجهيز النشر")

if "chars" not in st.session_state:
    st.session_state["chars"] = load_characters()
if "episode" not in st.session_state:
    st.session_state["episode"] = None
if "scene_assets" not in st.session_state:
    st.session_state["scene_assets"] = {}

tab1, tab2, tab3 = st.tabs(["1️⃣ الشخصيتان", "2️⃣ الاسكربت + SEO", "3️⃣ الإنتاج والمونتاج"])

with tab1:
    st.subheader("تصميم الصديقين (تُحفظ مرة واحدة لضمان الثبات)")
    chars = st.session_state["chars"]
    col1, col2 = st.columns(2)
    for num, col in [("1", col1), ("2", col2)]:
        with col:
            st.markdown(f"### الشخصية {num}")
            chars[f"char{num}_name"] = st.text_input(f"الاسم {num}", value=chars[f"char{num}_name"])
            chars[f"char{num}_voice"] = st.text_input(f"صوت ElevenLabs {num}", value=chars[f"char{num}_voice"])
            chars[f"char{num}_desc"] = st.text_area(f"الوصف البصري {num} (EN)", value=chars[f"char{num}_desc"], height=110)
            if st.button(f"🎨 توليد صورة مرجعية {num}"):
                if not fal_key:
                    st.error("أدخل مفتاح fal.ai أولاً.")
                else:
                    try:
                        with st.spinner("جاري الرسم..."):
                            res = fal_client.subscribe(
                                "google/nano-banana-2.1",
                                arguments={
                                    "prompt": f"Character reference portrait, front view, neutral studio background, {chars[f'char{num}_desc']}",
                                    "aspect_ratio": "3:4",
                                    "resolution": "2K",
                                },
                            )
                            chars[f"char{num}_url"] = res["images"][0]["url"]
                            save_characters(chars)
                            st.rerun()
                    except Exception as e:
                        st.error(f"خطأ: {e}")
            up = st.file_uploader(f"أو ارفع صورة {num}", type=["png", "jpg", "jpeg"], key=f"up{num}")
            if up and fal_key:
                try:
                    tmp = BASE_DIR / f"char{num}_upload.png"
                    tmp.write_bytes(up.read())
                    chars[f"char{num}_url"] = fal_client.upload_file(str(tmp))
                    save_characters(chars)
                    st.success("تم الرفع!")
                except Exception as e:
                    st.error(f"خطأ: {e}")
            if chars[f"char{num}_url"]:
                st.image(chars[f"char{num}_url"], width=260)
    if st.button("💾 حفظ الشخصيتين"):
        save_characters(chars)
        st.success("تم الحفظ!")

with tab2:
    st.subheader("كتابة الحلقة وتجهيزها للانتشار")
    dialects = [
        "العربية - اللهجة المصرية الكوميدية",
        "العربية - اللهجة السورية / الشامية",
        "العربية - اللهجة السعودية البيضاء",
        "العربية - اللهجة الخليجية",
        "العربية الفصحى المبسطة",
        "English (American Casual)",
        "Français",
        "Español",
    ]
    c1, c2 = st.columns(2)
    with c1:
        dialect1 = st.selectbox(f"لهجة {st.session_state['chars']['char1_name']}", dialects, index=0)
    with c2:
        dialect2 = st.selectbox(f"لهجة {st.session_state['chars']['char2_name']}", dialects, index=1)
    c3, c4 = st.columns(2)
    with c3:
        num_scenes = st.slider("عدد المشاهد", 2, 8, 4)
    with c4:
        tone = st.selectbox("الأسلوب", ["كوميدي يومي سريع", "موقف محرج ومضحك", "نقاش طريف", "نصيحة ساخرة"])
    idea = st.text_area("فكرة الحلقة (اختياري — اتركه فارغاً ليبتكر الذكاء الاصطناعي فكرة)")

    if st.button("✨ توليد الاسكربت والعناوين", type="primary"):
        if not gemini_key:
            st.error("أدخل Gemini API Key أولاً.")
        else:
            try:
                with st.spinner("جاري كتابة الحوار والعناوين..."):
                    client = genai.Client(api_key=gemini_key)
                    chars = st.session_state["chars"]
                    prompt = f"""
أنت مخرج محتوى فيروسي لمقاطع الكرتون القصيرة (Reels / Shorts / TikTok).
الشخصيتان صديقان مقربان:
- char1: {chars['char1_name']} — يتحدث دائماً بـ: {dialect1} | وصفه: {chars['char1_desc']}
- char2: {chars['char2_name']} — يتحدث دائماً بـ: {dialect2} | وصفه: {chars['char2_desc']}

المطلوب: حلقة من {num_scenes} مشاهد متسلسلة.
الأسلوب: {tone}
الفكرة: {idea if idea.strip() else "ابتكر فكرة يومية طريفة ومضحكة بين الصديقين."}

القواعد:
1. التزم بدقة أن يتحدث char1 بلهجته ({dialect1}) وchar2 بلهجته ({dialect2}) في جمل قصيرة طبيعية مضبوطة بالشكل لتسهيل النطق.
2. في image_prompt: اكتب بالإنجليزية وصف مشهد 9:16 يذكر Image 1 و/أو Image 2 بنفس التصميم والملابس مع وضوح الوجه للكاميرا.
3. في motion_prompt: اكتب بالإنجليزية وصف حركة المتحدث وتعبيرات وجهه.
4. اكتب 5 عناوين فيروسية، وصف منشور تفاعلي، و10 هاشتاغات.
"""
                    resp = None
                    last_err = None
                    for m_name in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]:
                        try:
                            resp = client.models.generate_content(
                                model=m_name,
                                contents=prompt,
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json",
                                    response_schema=EpisodePlan,
                                ),
                            )
                            break
                        except Exception as err:
                            last_err = err
                            time.sleep(1)
                    if resp is None:
                        raise last_err

                    plan = EpisodePlan.model_validate_json(resp.text)
                    st.session_state["episode"] = plan.model_dump()
                    st.session_state["scene_assets"] = {}
                    st.session_state.pop("current_run_dir", None)
                    st.session_state.pop("final_mp4", None)
                    st.success("تم توليد الحلقة بنجاح!")
            except Exception as e:
                st.error(f"خطأ في التوليد: {e}")

    if st.session_state["episode"]:
        ep = st.session_state["episode"]
        st.markdown(f"### 📌 {ep['episode_title']}")
        with st.expander("🚀 العناوين والوصف والهاشتاغات", expanded=True):
            for t in ep["viral_titles"]:
                st.write(f"- {t}")
            st.text_area("وصف المنشور", value=ep["post_description"], key="seo_desc")
            st.code(" ".join(ep["hashtags"]))
        for idx, sc in enumerate(ep["scenes"]):
            with st.container(border=True):
                sp = st.session_state["chars"]["char1_name"] if sc["speaker"] == "char1" else st.session_state["chars"]["char2_name"]
                st.markdown(f"**المشهد {sc['scene_number']} — {sp}**")
                sc["dialogue"] = st.text_input("الحوار", value=sc["dialogue"], key=f"dlg_{idx}")
                sc["image_prompt"] = st.text_area("أمر الصورة (EN)", value=sc["image_prompt"], key=f"imgp_{idx}", height=70)
                sc["motion_prompt"] = st.text_input("أمر الحركة (EN)", value=sc["motion_prompt"], key=f"motp_{idx}")

with tab3:
    if not st.session_state["episode"]:
        st.info("ولّد الاسكربت من التبويب الثاني أولاً.")
    else:
        ep = st.session_state["episode"]
        chars = st.session_state["chars"]
        use_lipsync = st.checkbox("تفعيل مزامنة الشفاه (Kling Lip-Sync)", value=True)
        if "current_run_dir" not in st.session_state:
            run_dir = BASE_DIR / f"episode_{int(time.time())}"
            run_dir.mkdir(parents=True, exist_ok=True)
            st.session_state["current_run_dir"] = str(run_dir)
        ep_dir = Path(st.session_state["current_run_dir"])
        ref_urls = [u for u in [chars.get("char1_url"), chars.get("char2_url")] if u]

        for idx, sc in enumerate(ep["scenes"]):
            assets = st.session_state["scene_assets"].setdefault(idx, {})
            sp_name = chars["char1_name"] if sc["speaker"] == "char1" else chars["char2_name"]
            v_name = chars["char1_voice"] if sc["speaker"] == "char1" else chars["char2_voice"]
            with st.container(border=True):
                st.markdown(f"#### المشهد {sc['scene_number']}: {sp_name}")
                st.write(f"💬 _{sc['dialogue']}_")
                c_img, c_aud, c_vid = st.columns(3)
                with c_img:
                    if st.button("🖼️ توليد الصورة", key=f"gi_{idx}"):
                        try:
                            with st.spinner("جاري الرسم..."):
                                model_id = "google/nano-banana-2.1/edit" if ref_urls else "google/nano-banana-2.1"
                                args = {"prompt": sc["image_prompt"], "aspect_ratio": "9:16", "resolution": "1K"}
                                if ref_urls:
                                    args["image_urls"] = ref_urls
                                res = fal_client.subscribe(model_id, arguments=args)
                                img_url = res["images"][0]["url"]
                                lp = ep_dir / f"scene_{idx}.png"
                                download_file(img_url, lp)
                                assets["image_url"] = img_url
                                assets["image_path"] = str(lp)
                                st.rerun()
                        except Exception as e:
                            st.error(f"خطأ: {e}")
                    if assets.get("image_path") and Path(assets["image_path"]).exists():
                        st.image(assets["image_path"])
                with c_aud:
                    if st.button("🎙️ توليد الصوت", key=f"ga_{idx}"):
                        try:
                            with st.spinner("جاري التوليد..."):
                                res = fal_client.subscribe(
                                    "fal-ai/elevenlabs/tts/eleven-v3",
                                    arguments={"text": f"{sc['emotion_tag']} {sc['dialogue']}", "voice": v_name, "stability": 0.45, "similarity_boost": 0.75},
                                )
                                aud_url = res["audio"]["url"]
                                la = ep_dir / f"scene_{idx}.mp3"
                                download_file(aud_url, la)
                                padded = ensure_min_audio_duration(la, 2.2)
                                if padded != la:
                                    aud_url = fal_client.upload_file(str(padded))
                                    la = padded
                                assets["audio_url"] = aud_url
                                assets["audio_path"] = str(la)
                                st.rerun()
                        except Exception as e:
                            st.error(f"خطأ: {e}")
                    up_a = st.file_uploader("أو ارفع صوتك", type=["mp3", "wav", "m4a"], key=f"ua_{idx}")
                    if up_a and fal_key:
                        try:
                            la = ep_dir / f"custom_{idx}_{up_a.name}"
                            la.write_bytes(up_a.read())
                            padded = ensure_min_audio_duration(la, 2.2)
                            assets["audio_url"] = fal_client.upload_file(str(padded))
                            assets["audio_path"] = str(padded)
                            st.success("تم اعتماد الصوت!")
                        except Exception as e:
                            st.error(f"خطأ: {e}")
                    if assets.get("audio_path") and Path(assets["audio_path"]).exists():
                        st.audio(assets["audio_path"])
                with c_vid:
                    ready = bool(assets.get("image_url") and assets.get("audio_url"))
                    if st.button("🎥 إنتاج المشهد", key=f"gv_{idx}", disabled=not ready):
                        try:
                            with st.spinner("جاري التحريك..."):
                                vr = fal_client.subscribe(
                                    "fal-ai/kling-video/o3/standard/image-to-video",
                                    arguments={"image_url": assets["image_url"], "prompt": sc["motion_prompt"], "duration": "5", "generate_audio": False},
                                )
                                raw_url = vr["video"]["url"]
                                fp = ep_dir / f"scene_{idx}_final.mp4"
                                if use_lipsync:
                                    sr = fal_client.subscribe(
                                        "fal-ai/kling-video/lipsync/audio-to-video",
                                        arguments={"video_url": raw_url, "audio_url": assets["audio_url"]},
                                    )
                                    download_file(sr["video"]["url"], fp)
                                else:
                                    rp = ep_dir / f"scene_{idx}_raw.mp4"
                                    download_file(raw_url, rp)
                                    merge_video_and_audio(rp, Path(assets["audio_path"]), fp)
                                assets["video_path"] = str(fp)
                                st.rerun()
                        except Exception as e:
                            st.error(f"خطأ: {e}")
                    if assets.get("video_path") and Path(assets["video_path"]).exists():
                        st.video(assets["video_path"])

        st.divider()
        clips = [Path(st.session_state["scene_assets"][i]["video_path"]) for i in range(len(ep["scenes"])) if st.session_state["scene_assets"].get(i, {}).get("video_path")]
        if len(clips) == len(ep["scenes"]) and len(clips) > 0:
            if st.button("🎞️ دمج الحلقة كاملة", type="primary"):
                try:
                    with st.spinner("جاري الدمج النهائي..."):
                        out = ep_dir / "FINAL_EPISODE_9x16.mp4"
                        concat_episode_clips(clips, out)
                        st.session_state["final_mp4"] = str(out)
                        st.success("🎉 الحلقة جاهزة!")
                except Exception as e:
                    st.error(f"خطأ في الدمج: {e}")
        if st.session_state.get("final_mp4") and Path(st.session_state["final_mp4"]).exists():
            st.video(st.session_state["final_mp4"])
            with open(st.session_state["final_mp4"], "rb") as f:
                st.download_button("⬇️ تحميل الفيديو النهائي (MP4)", f, file_name="cartoon_episode_9x16.mp4")

# END_OF_APP
