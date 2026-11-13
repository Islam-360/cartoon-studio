import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List
from google import genai
from google.genai import types
from pydantic import BaseModel
import streamlit as st

BASE_DIR = Path("studio_workspace")
BASE_DIR.mkdir(exist_ok=True)
CHAR_FILE = BASE_DIR / "characters.json"

st.set_page_config(page_title="استوديو الكرتون المجاني", page_icon="🎬", layout="wide")

VOICE_OPTIONS = {
    "ar-EG-ShakirNeural": "مصر - صوت شاب (مناسب لخسة)",
    "ar-EG-SalmaNeural": "مصر - صوت بنت",
    "ar-SY-AmanyNeural": "سوريا - صوت بنت (مناسب للفتة)",
    "ar-SY-LaithNeural": "سوريا - صوت شاب",
    "ar-SA-HamedNeural": "السعودية - صوت شاب",
    "ar-SA-ZariyahNeural": "السعودية - صوت بنت",
    "ar-LB-LaylaNeural": "لبنان - صوت بنت",
    "ar-AE-HamdanNeural": "الإمارات - صوت شاب",
    "en-US-AndrewMultilingualNeural": "إنجليزي / متعدد اللغات (شاب)",
    "en-US-AvaMultilingualNeural": "إنجليزي / متعدد اللغات (بنت)",
}

class SceneItem(BaseModel):
    scene_number: int
    speaker: str
    dialogue: str
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

def get_audio_duration(audio_path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True
    )
    try:
        return max(float(probe.stdout.strip()), 1.5)
    except ValueError:
        return 3.0

def generate_free_tts(text: str, voice_id: str, out_path: Path):
    clean_text = text.replace("\n", " ").strip()
    subprocess.run(
        ["edge-tts", "--voice", voice_id, "--text", clean_text, "--write-media", str(out_path)],
        check=True, capture_output=True, text=True
    )

def image_to_animated_clip(img_path: Path, audio_path: Path, out_path: Path):
    dur = get_audio_duration(audio_path)
    frames = max(int(dur * 24) + 6, 36)
    vf = (
        f"[0:v]scale=2160:3840:force_original_aspect_ratio=increase,"
        f"crop=2160:3840,"
        f"zoompan=z='min(zoom+0.0012,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=24[v]"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(img_path), "-i", str(audio_path),
            "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(out_path)
        ],
        check=True, capture_output=True
    )

def video_with_audio_clip(vid_path: Path, audio_path: Path, out_path: Path):
    subprocess.run(
        [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(vid_path), "-i", str(audio_path),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(out_path)
        ],
        check=True, capture_output=True
    )

def concat_episode_clips(clip_paths: List[Path], final_output: Path):
    list_file = final_output.with_suffix(".txt")
    list_file.write_text("\n".join([f"file '{p.resolve()}'" for p in clip_paths]), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(final_output)],
        check=True, capture_output=True
    )

def load_characters():
    if CHAR_FILE.exists():
        return json.loads(CHAR_FILE.read_text(encoding="utf-8"))
    return {
        "char1_name": "خسة",
        "char1_desc": "A funny 3D Pixar-style cartoon Egyptian young man in his 20s, wearing a trendy casual hoodie and jeans, expressive big eyes, witty smile",
        "char1_voice": "ar-EG-ShakirNeural",
        "char1_img": "",
        "char2_name": "لفتة",
        "char2_desc": "A charming funny 3D Pixar-style cartoon Syrian young woman in her 20s, wearing a stylish modern jacket and jeans, expressive bright eyes, friendly smile",
        "char2_voice": "ar-SY-AmanyNeural",
        "char2_img": "",
    }

def save_characters(data: dict):
    CHAR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

with st.sidebar:
    st.header("🔑 إعدادات النسخة المجانية")
    gemini_key = st.text_input("Gemini API Key (مجاني)", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key
    st.divider()
    st.success("🎙️ الصوت المجاني (Edge TTS) مفعّل بدون مفتاح!")
    if check_ffmpeg():
        st.success("✅ FFmpeg جاهز للمونتاج")
    else:
        st.error("⚠️ FFmpeg غير مثبت")

st.title("🎬 استوديو يوميات الكرتون (النسخة المجانية 100%)")
st.caption("اسكربت مجاني بلهجتين + أصوات عربية مجانية + تحريك ومونتاج مجاني")

if "chars" not in st.session_state:
    st.session_state["chars"] = load_characters()
if "episode" not in st.session_state:
    st.session_state["episode"] = None
if "scene_assets" not in st.session_state:
    st.session_state["scene_assets"] = {}

tab1, tab2, tab3 = st.tabs(["1️⃣ الشخصيتان", "2️⃣ الاسكربت + SEO", "3️⃣ الإنتاج المجاني"])

with tab1:
    st.subheader("إعداد الشخصيتين وأصواتهما المجانية")
    chars = st.session_state["chars"]
    col1, col2 = st.columns(2)
    voice_keys = list(VOICE_OPTIONS.keys())
    for num, col in [("1", col1), ("2", col2)]:
        with col:
            st.markdown(f"### الشخصية {num}")
            chars[f"char{num}_name"] = st.text_input(f"الاسم {num}", value=chars[f"char{num}_name"])
            cur_v = chars.get(f"char{num}_voice", voice_keys[0])
            idx_v = voice_keys.index(cur_v) if cur_v in voice_keys else 0
            chars[f"char{num}_voice"] = st.selectbox(
                f"الصوت المجاني {num}", voice_keys, index=idx_v,
                format_func=lambda x: VOICE_OPTIONS[x], key=f"v_{num}"
            )
            chars[f"char{num}_desc"] = st.text_area(f"الوصف البصري {num} (EN)", value=chars[f"char{num}_desc"], height=100)
            up = st.file_uploader(f"ارفع صورة ثابتة للشخصية {num} (من Gemini/Dreamina مجاناً)", type=["png", "jpg", "jpeg"], key=f"up{num}")
            if up:
                p = BASE_DIR / f"char{num}_ref.png"
                p.write_bytes(up.read())
                chars[f"char{num}_img"] = str(p)
                save_characters(chars)
                st.success("تم حفظ الصورة!")
            if chars.get(f"char{num}_img") and Path(chars[f"char{num}_img"]).exists():
                st.image(chars[f"char{num}_img"], width=240)
    if st.button("💾 حفظ بيانات الشخصيتين"):
        save_characters(chars)
        st.success("تم الحفظ!")

with tab2:
    st.subheader("كتابة الحلقة مجاناً وتجهيز العناوين")
    dialects = [
        "العربية - اللهجة المصرية الكوميدية",
        "العربية - اللهجة السورية / الشامية",
        "العربية - اللهجة السعودية البيضاء",
        "العربية - اللهجة الخليجية",
        "العربية الفصحى المبسطة",
        "English (American Casual)",
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
    idea = st.text_area("فكرة الحلقة (اختياري)")

    if st.button("✨ توليد الاسكربت والعناوين (مجاناً)", type="primary"):
        if not gemini_key:
            st.error("أدخل Gemini API Key في القائمة الجانبية أولاً.")
        else:
            try:
                with st.spinner("جاري كتابة الحوار والعناوين..."):
                    client = genai.Client(api_key=gemini_key)
                    chars = st.session_state["chars"]
                    prompt = f"""
أنت كاتب محتوى فيروسي لمقاطع الكرتون القصيرة (Reels / Shorts / TikTok).
الشخصيتان صديقان:
- speaker="char1" واسمه ({chars['char1_name']}): يتحدث دائماً بـ {dialect1}. وصفه: {chars['char1_desc']}
- speaker="char2" واسمه ({chars['char2_name']}): يتحدث دائماً بـ {dialect2}. وصفه: {chars['char2_desc']}

المطلوب: حلقة من {num_scenes} مشاهد متسلسلة بأسلوب ({tone}).
الفكرة: {idea if idea.strip() else "ابتكر فكرة يومية كوميدية بينهما."}

القواعد الصارمة:
1. التزم أن تكون قيمة speaker إما "char1" أو "char2" بدقة، وأن يتكلم "char1" بـ({dialect1}) فقط، و"char2" بـ({dialect2}) فقط.
2. جمل قصيرة مضبوطة بالشكل عند الكلمات الملتبسة لتنطق بشكل سليم.
3. image_prompt: وصف إنجليزي جاهز لنسخه في مولد صور مجاني لإنتاج لقطة كرتونية ثلاثية الأبعاد عمودية 9:16.
4. motion_prompt: وصف إنجليزي قصير للحركة.
5. 5 عناوين فيروسية، وصف منشور تفاعلي، و10 هاشتاغات.
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
                    st.success("تم توليد الحلقة مجاناً بنجاح!")
            except Exception as e:
                st.error(f"خطأ: {e}")

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

with tab3:
    if not st.session_state["episode"]:
        st.info("ولّد الاسكربت من التبويب الثاني أولاً.")
    else:
        ep = st.session_state["episode"]
        chars = st.session_state["chars"]
        if "current_run_dir" not in st.session_state:
            run_dir = BASE_DIR / f"free_ep_{int(time.time())}"
            run_dir.mkdir(parents=True, exist_ok=True)
            st.session_state["current_run_dir"] = str(run_dir)
        ep_dir = Path(st.session_state["current_run_dir"])

        st.info("💡 انسخ وصف الصورة من كل مشهد إلى تطبيق Gemini أو Dreamina مجاناً، ثم ارفع الصورة (أو الفيديو من Google Flow) هنا!")

        for idx, sc in enumerate(ep["scenes"]):
            assets = st.session_state["scene_assets"].setdefault(idx, {})
            is_c1 = sc["speaker"] == "char1"
            sp_name = chars["char1_name"] if is_c1 else chars["char2_name"]
            v_id = chars["char1_voice"] if is_c1 else chars["char2_voice"]
            char_img = chars.get("char1_img") if is_c1 else chars.get("char2_img")

            with st.container(border=True):
                st.markdown(f"#### المشهد {sc['scene_number']}: {sp_name}")
                st.write(f"💬 _{sc['dialogue']}_")
                with st.expander("📋 انسخ وصف الصورة/الفيديو للمواقع المجانية"):
                    st.code(sc["image_prompt"])

                c_aud, c_vis, c_out = st.columns(3)
                with c_aud:
                    if st.button("🎙️ توليد صوت مجاني (Edge TTS)", key=f"f_aud_{idx}"):
                        try:
                            with st.spinner("جاري التوليد مجاناً..."):
                                ap = ep_dir / f"aud_{idx}.mp3"
                                generate_free_tts(sc["dialogue"], v_id, ap)
                                assets["audio_path"] = str(ap)
                                st.rerun()
                        except Exception as e:
                            st.error(f"خطأ: {e}")
                    up_a = st.file_uploader("أو ارفع صوتك", type=["mp3", "wav", "m4a"], key=f"ua_{idx}")
                    if up_a:
                        ap = ep_dir / f"custom_{idx}_{up_a.name}"
                        ap.write_bytes(up_a.read())
                        assets["audio_path"] = str(ap)
                    if assets.get("audio_path") and Path(assets["audio_path"]).exists():
                        st.audio(assets["audio_path"])

                with c_vis:
                    up_v = st.file_uploader("ارفع صورة أو فيديو المشهد", type=["png", "jpg", "jpeg", "mp4", "mov"], key=f"uv_{idx}")
                    if up_v:
                        ext = Path(up_v.name).suffix.lower()
                        vp = ep_dir / f"vis_{idx}{ext}"
                        vp.write_bytes(up_v.read())
                        assets["visual_path"] = str(vp)
                        assets["is_video"] = ext in [".mp4", ".mov"]
                    if char_img and Path(char_img).exists():
                        if st.button(f"🖼️ استخدام صورة {sp_name} المحفوظة", key=f"use_ref_{idx}"):
                            assets["visual_path"] = char_img
                            assets["is_video"] = False
                            st.rerun()
                    if assets.get("visual_path") and Path(assets["visual_path"]).exists():
                        if assets.get("is_video"):
                            st.video(assets["visual_path"])
                        else:
                            st.image(assets["visual_path"], width=180)

                with c_out:
                    can_build = bool(assets.get("audio_path") and assets.get("visual_path"))
                    if st.button("🎬 تجهيز مقطع المشهد", key=f"mk_{idx}", disabled=not can_build):
                        try:
                            with st.spinner("جاري دمج وتحريك المشهد..."):
                                out_clip = ep_dir / f"clip_{idx}.mp4"
                                if assets.get("is_video"):
                                    video_with_audio_clip(Path(assets["visual_path"]), Path(assets["audio_path"]), out_clip)
                                else:
                                    image_to_animated_clip(Path(assets["visual_path"]), Path(assets["audio_path"]), out_clip)
                                assets["clip_path"] = str(out_clip)
                                st.rerun()
                        except Exception as e:
                            st.error(f"خطأ: {e}")
                    if assets.get("clip_path") and Path(assets["clip_path"]).exists():
                        st.video(assets["clip_path"])

        st.divider()
        ready = [Path(st.session_state["scene_assets"][i]["clip_path"]) for i in range(len(ep["scenes"])) if st.session_state["scene_assets"].get(i, {}).get("clip_path")]
        if len(ready) == len(ep["scenes"]) and len(ready) > 0:
            if st.button("🎞️ دمج الحلقة كاملة (مجاناً)", type="primary"):
                try:
                    with st.spinner("جاري المونتاج النهائي..."):
                        out = ep_dir / "FREE_EPISODE_9x16.mp4"
                        concat_episode_clips(ready, out)
                        st.session_state["final_mp4"] = str(out)
                        st.success("🎉 الحلقة جاهزة للنشر مجاناً 100%!")
                except Exception as e:
                    st.error(f"خطأ في الدمج: {e}")
        if st.session_state.get("final_mp4") and Path(st.session_state["final_mp4"]).exists():
            st.video(st.session_state["final_mp4"])
            with open(st.session_state["final_mp4"], "rb") as f:
                st.download_button("⬇️ تحميل الفيديو النهائي (MP4)", f, file_name="free_cartoon_episode.mp4")

# END_OF_APP
