import os
import shutil
import zipfile
import subprocess
import telebot
import platform
import urllib.request
import hashlib
import tarfile
from pathlib import Path

# ==========================================
# ১. কনফিগারেশন এবং ভেরিয়েবল
# ==========================================
BOT_TOKEN = "9097454535:AAGKAwMXkTxsQ1dTxgZwLXxE0doH0AfFOKg"
CMD_INSTALL = ["npm", "install"]
BASE_DIR = Path("./bot_workspace").absolute()
BASE_DIR.mkdir(exist_ok=True)
CACHE_DIR = BASE_DIR / "npm_cache"
CACHE_DIR.mkdir(exist_ok=True)
LIBS_DIR = BASE_DIR / "chrome_libs"

user_projects = {}

# ==========================================
# ২. অটো-ইনস্টলার (Node.js এবং Chrome Libs)
# ==========================================
def ensure_node_installed():
    if shutil.which("npm"):
        return True
        
    arch = "arm64" if platform.machine().lower() in ["aarch64", "arm64"] else "x64"
    node_version = "v20.11.1"
    download_url = f"https://nodejs.org/dist/{node_version}/node-{node_version}-linux-{arch}.tar.xz"
    
    install_dir = BASE_DIR / "nodejs"
    install_dir.mkdir(exist_ok=True)
    tar_file = BASE_DIR / "node.tar.xz"
    
    print(f"⏳ Node.js {node_version} ({arch}) ডাউনলোড হচ্ছে...")
    try:
        urllib.request.urlretrieve(download_url, tar_file)
    except Exception as e:
        print(f"ডাউনলোড ব্যর্থ: {e}")
        return False
    
    print("📦 Node.js আনজিপ করা হচ্ছে...")
    try:
        with tarfile.open(tar_file, "r:xz") as tar:
            try:
                tar.extractall(path=install_dir, filter="data")
            except TypeError:
                tar.extractall(path=install_dir)
        tar_file.unlink()
    except Exception as e:
        print(f"আনজিপ ব্যর্থ: {e}")
        return False
    
    node_bin = None
    for p in install_dir.iterdir():
        if p.is_dir() and (p / "bin" / "node").exists():
            node_bin = p / "bin"
            break
    
    if node_bin:
        os.environ["PATH"] = str(node_bin) + os.pathsep + os.environ.get("PATH", "")
        print(f"✅ Node.js ইনস্টল সম্পন্ন: {node_bin}")
        return True
    print("❌ Node.js বাইনারি পাওয়া যায়নি")
    return False

def ensure_chrome_libs():
    if not platform.system() == "Linux":
        return
    print("⏳ Chrome সিস্টেম লাইব্রেরি প্রসেস করা হচ্ছে...")
    try:
        LIBS_DIR.mkdir(parents=True, exist_ok=True)
        arch = "arm64" if platform.machine().lower() in ["aarch64", "arm64"] else "amd64"
        packages = ["libnspr4", "libnss3", "libasound2"]
        
        for pkg in packages:
            try:
                res = subprocess.run(["sudo", "apt-get", "download", pkg], cwd=str(LIBS_DIR), capture_output=True, text=True)
                if res.returncode != 0:
                    if arch == "arm64":
                        urls = {
                            "libnspr4": "http://ports.ubuntu.com/pool/main/n/nspr/libnspr4_4.35-1_arm64.deb",
                            "libnss3": "http://ports.ubuntu.com/pool/main/n/nss/libnss3_3.98-0ubuntu0.22.04.1_arm64.deb",
                            "libasound2": "http://ports.ubuntu.com/pool/main/a/alsa-lib/libasound2_1.2.6.1-1ubuntu1_arm64.deb"
                        }
                    else:
                        urls = {
                            "libnspr4": "http://archive.ubuntu.com/ubuntu/pool/main/n/nspr/libnspr4_4.35-1_amd64.deb",
                            "libnss3": "http://archive.ubuntu.com/ubuntu/pool/main/n/nss/libnss3_3.98-0ubuntu0.22.04.1_amd64.deb",
                            "libasound2": "http://archive.ubuntu.com/ubuntu/pool/main/a/alsa-lib/libasound2_1.2.6.1-1ubuntu1_amd64.deb"
                        }
                    if pkg in urls:
                        urllib.request.urlretrieve(urls[pkg], LIBS_DIR / f"{pkg}.deb")
            except Exception as e:
                print(f"  ❌ {pkg} ডাউনলোড এরর: {e}")

        for deb in list(LIBS_DIR.glob("*.deb")):
            try:
                subprocess.run(["dpkg-deb", "-x", str(deb), str(LIBS_DIR)], check=True, capture_output=True)
                deb.unlink()
            except Exception as e:
                print(f"  ❌ আনপ্যাক এরর: {e}")

        for p in LIBS_DIR.rglob("libnspr4.so*"):
            lib_dir = p.parent
            os.environ["LD_LIBRARY_PATH"] = str(lib_dir) + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
            print(f"✅ LD_LIBRARY_PATH সেট: {lib_dir}")
            break
    except Exception as e:
        print(f"Chrome libs setup error: {e}")

def find_remotion_chrome_dir(project_root: Path):
    remotion_base = project_root / "node_modules" / ".remotion" / "chrome-headless-shell"
    if not remotion_base.exists():
        return None
    for arch_dir in remotion_base.iterdir():
        if not arch_dir.is_dir():
            continue
        for inner in arch_dir.iterdir():
            if inner.is_dir():
                return inner
    return None

def copy_libs_to_chrome(project_root: Path):
    if not platform.system() == "Linux":
        return False
    chrome_dir = find_remotion_chrome_dir(project_root)
    if not chrome_dir:
        return False
    count = 0
    for so_file in LIBS_DIR.rglob("*.so*"):
        if so_file.is_file():
            try:
                shutil.copy2(so_file, chrome_dir / so_file.name)
                count += 1
            except Exception:
                pass
    print(f"✅ {count} টি লাইব্রেরি কপি সম্পন্ন")
    return True

def ensure_remotion_browser(project_root: Path):
    print("⏳ Remotion Chrome প্রস্তুত করা হচ্ছে...")
    try:
        result = subprocess.run(
            ["npx", "remotion", "browser", "ensure"],
            cwd=project_root, capture_output=True, text=True, timeout=900,
            env={**os.environ}
        )
        return result.returncode == 0
    except Exception as e:
        print(f"browser ensure ব্যর্থ: {e}")
        return False

# ==========================================
# ৩. বট ইনিশিয়ালাইজ
# ==========================================
if not ensure_node_installed():
    print("🚨 Node.js ছাড়া বট চলবে না।")
    exit(1)

ensure_chrome_libs()

bot = telebot.TeleBot(BOT_TOKEN)

def find_project_root(extract_path: Path) -> Path:
    """সঠিক প্রজেক্ট রুট খুঁজে বের করে যেখানে package.json আছে"""
    if (extract_path / "package.json").exists():
        return extract_path
    for item in extract_path.iterdir():
        if item.is_dir() and (item / "package.json").exists():
            return item
    for pkg in extract_path.rglob("package.json"):
        if "node_modules" not in str(pkg):
            return pkg.parent
    return extract_path

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "স্বাগতম! আমাকে একটি `.zip` ফাইল পাঠান। আমি সেটি এক্সট্রাক্ট করে `npm install` করব।\n\nএরপর আপনি যেকোনো কমান্ড (যেমন: `npx remotion render src/index.ts Main out/video.mp4` অথবা শুধু `render`) পাঠালে আমি সেটি রান করে আউটপুট ও ভিডিও পাঠাবো।")

@bot.message_handler(content_types=['document'])
def handle_zip(message):
    file_name = message.document.file_name
    if not file_name.lower().endswith('.zip'):
        bot.reply_to(message, "দয়া করে শুধুমাত্র `.zip` ফাইল পাঠান।")
        return
    
    chat_id = message.chat.id
    status_msg = bot.reply_to(message, "📥 জিপ ফাইল ডাউনলোড হচ্ছে...")
    work_dir = BASE_DIR / str(chat_id)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        zip_path = work_dir / "source.zip"
        with open(zip_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        bot.edit_message_text("📦 জিপ ফাইল এক্সট্রাক্ট হচ্ছে...", chat_id, status_msg.message_id)
        extract_dir = work_dir / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        project_root = find_project_root(extract_dir)
        user_projects[chat_id] = project_root
        zip_path.unlink()
        
        pkg_json_path = project_root / "package.json"
        pkg_hash = ""
        if pkg_json_path.exists():
            pkg_hash = hashlib.md5(pkg_json_path.read_bytes()).hexdigest()
        
        cached_modules = CACHE_DIR / pkg_hash
        skip_install = False
        
        if cached_modules.exists() and pkg_hash != "":
            bot.edit_message_text("⚡ ক্যাশ থেকে `node_modules` কপি করা হচ্ছে...", chat_id, status_msg.message_id)
            try:
                if (project_root / "node_modules").exists():
                    shutil.rmtree(project_root / "node_modules")
                shutil.copytree(cached_modules, project_root / "node_modules")
                skip_install = True
            except Exception as e:
                print(f"Cache copy error: {e}")
        
        if not skip_install:
            bot.edit_message_text(f"📂 প্রজেক্ট: `{project_root.name}`\n\n⚙️ `npm install` চলছে...", chat_id, status_msg.message_id, parse_mode='Markdown')
            try:
                install_result = subprocess.run(CMD_INSTALL, cwd=project_root, capture_output=True, text=True, timeout=600)
                if install_result.returncode != 0:
                    error_detail = install_result.stderr[-1000:] if install_result.stderr else "Unknown error"
                    bot.edit_message_text(f"❌ `npm install` ব্যর্থ:\n```\n{error_detail}\n```", chat_id, status_msg.message_id, parse_mode='Markdown')
                    return
                
                if (project_root / "node_modules").exists() and pkg_hash != "":
                    try:
                        if cached_modules.exists():
                            shutil.rmtree(cached_modules)
                        shutil.copytree(project_root / "node_modules", cached_modules)
                    except Exception as e:
                        print(f"Cache save error: {e}")
            except Exception as e:
                bot.edit_message_text(f"❌ `npm install` ত্রুটি: {str(e)}", chat_id, status_msg.message_id)
                return

        bot.edit_message_text("✅ `npm install` সফল!\n\n💬 এখন আপনার রেন্ডার কমান্ডটি পাঠান (যেমন: `npx remotion render src/index.ts Main out/video.mp4` অথবা শুধু `render` লিখুন)।", chat_id, status_msg.message_id, parse_mode='Markdown')
            
    except Exception as e:
        bot.reply_to(message, f"❌ ত্রুটি: {str(e)}")

# ==========================================
# ৪. কমান্ড এক্সিকিউটর
# ==========================================
@bot.message_handler(func=lambda message: True)
def execute_custom_command(message):
    chat_id = message.chat.id
    cmd = message.text.strip()
    
    if chat_id not in user_projects or not user_projects[chat_id].exists():
        bot.reply_to(message, "❌ কোনো সক্রিয় প্রজেক্ট নেই। প্রথমে `.zip` ফাইল পাঠান।")
        return
        
    project_root = user_projects[chat_id]
    is_render = "remotion" in cmd and "render" in cmd
    
    # অটো-ডিটেকশন লজিক
    if cmd.lower() == "render" or is_render:
        # এন্ট্রি পয়েন্ট ফাইলটি খুঁজে বের করা (index.ts বা entry.ts)
        entry_file = None
        src_dir = project_root / "src"
        if src_dir.exists():
            if (src_dir / "index.ts").exists():
                entry_file = "src/index.ts"
            elif (src_dir / "entry.ts").exists():
                entry_file = "src/entry.ts"
            elif (src_dir / "index.tsx").exists():
                entry_file = "src/index.tsx"
            elif (src_dir / "entry.tsx").exists():
                entry_file = "src/entry.tsx"
        
        if not entry_file:
            bot.reply_to(message, "❌ `src` ফোল্ডারে কোনো এন্ট্রি পয়েন্ট (index.ts/entry.ts) পাওয়া যায়নি।")
            return
        
        if cmd.lower() == "render":
            # যদি ইউজার শুধু 'render' লিখে পাঠায়, তবে ডিফল্ট কমান্ড তৈরি হবে
            cmd = f"npx remotion render {entry_file} Main out/video.mp4"
        else:
            # যদি ইউজার নিজে কমান্ড লিখে পাঠায়, তবে তার মধ্যে থাকা ভুল পাথ ঠিক করে দেওয়া হবে
            for wrong_path in ["src/index.ts", "src/entry.ts", "src/index.tsx", "src/entry.tsx"]:
                if wrong_path in cmd:
                    cmd = cmd.replace(wrong_path, entry_file)
                    break
            else:
                # যদি কমান্ডে কোনো পাথ না থাকে, তবে ডিফল্ট পাথ জুড়ে দেওয়া হবে
                cmd = f"npx remotion render {entry_file} Main out/video.mp4"

    if is_render or cmd.lower().startswith("npx remotion render"):
        status_msg = bot.reply_to(message, "⏳ প্রথমে Chrome প্রস্তুত করা হচ্ছে...")
        ensure_remotion_browser(project_root)
        copy_libs_to_chrome(project_root)
        bot.edit_message_text(f"⏳ কমান্ড রান হচ্ছে...\n`{cmd}`", chat_id, status_msg.message_id, parse_mode='Markdown')
    else:
        status_msg = bot.reply_to(message, f"⏳ কমান্ড রান হচ্ছে...\n`{cmd}`", parse_mode='Markdown')
    
    try:
        # এখানে sudo যোগ করা হলো যাতে সিস্টেম লেভেলে কোনো সমস্যা না হয়
        result = subprocess.run(cmd, shell=True, cwd=project_root, capture_output=True, text=True, timeout=1800)
        output = result.stdout + "\n" + result.stderr
        
        if "remotion render" in cmd and ("error while loading shared libraries" in output or "cannot open shared object file" in output):
            bot.send_message(chat_id, "🔄 Chrome লাইব্রেরি সমস্যা, পুনরায় রেন্ডার চেষ্টা...")
            copy_libs_to_chrome(project_root)
            result = subprocess.run(cmd, shell=True, cwd=project_root, capture_output=True, text=True, timeout=1800)
            output = result.stdout + "\n" + result.stderr

        if not output.strip():
            output = "✅ কমান্ড সম্পন্ন (আউটপুট নেই)।"
        if len(output) > 4000:
            output = output[:3900] + "\n\n... (কাটা হয়েছে)"
            
        bot.edit_message_text(f"📝 **আউটপুট:**\n```bash\n{output}\n```", chat_id, status_msg.message_id, parse_mode='Markdown')
        
    except subprocess.TimeoutExpired:
        bot.edit_message_text("❌ কমান্ড টাইমআউট (৩০ মিনিট)।", chat_id, status_msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ ত্রুটি:\n{str(e)}", chat_id, status_msg.message_id)
        return

    if "remotion render" in cmd:
        video_path = None
        out_folder = project_root / "out"
        if out_folder.exists():
            mp4_files = list(out_folder.glob("*.mp4"))
            if mp4_files:
                video_path = mp4_files[0]
        
        if video_path and video_path.exists():
            try:
                with open(video_path, 'rb') as video_file:
                    bot.send_video(chat_id, video_file, caption="🎬 ভিডিও তৈরি হয়েছে!")
                video_path.unlink()
            except Exception as e:
                bot.send_message(chat_id, f"⚠️ ভিডিও পাঠাতে সমস্যা: {e}")

if __name__ == "__main__":
    print("বট চালু হচ্ছে...")
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"Polling Error: {e}")
