// RAG プロンプトビルダー（デスクトップ版）
// 同じフォルダの rag.exe を「rag serve --port 0」で起動し、表示された http://127.0.0.1:ポート/ をウィンドウで開くだけの薄い殻。
// 検索・ベクトル化（ネイティブ版エンジン）・画面はすべて rag.exe 側にある。外部とは通信しない。
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::time::Duration;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// 終了時に止めるための rag.exe のプロセス
struct Backend(Mutex<Option<Child>>);

fn exe_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."))
}

/// rag.exe を起動して、画面の URL（1行目の出力）を受け取る
fn start_backend() -> Result<(Child, String), String> {
    let dir = exe_dir();
    let rag = dir.join(if cfg!(windows) { "rag.exe" } else { "rag" });
    if !rag.exists() {
        return Err(format!("{} が見つかりません。配布フォルダの中身をすべて同じ場所に置いてください。", rag.display()));
    }
    let mut cmd = Command::new(&rag);
    cmd.args(["serve", "--port", "0", "--print-url"])
        .current_dir(&dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW：黒い画面を出さない
    let mut child = cmd.spawn().map_err(|e| format!("rag.exe を起動できません: {e}"))?;
    let stdout = child.stdout.take().ok_or("rag.exe の出力を受け取れません")?;
    let (tx, rx) = mpsc::channel::<String>();
    std::thread::spawn(move || {
        // 1行目（URL）を渡したあとも読み続ける（パイプを閉じると rag.exe 側が書き込みに失敗するため）
        let mut lines = BufReader::new(stdout).lines();
        if let Some(Ok(first)) = lines.next() {
            let _ = tx.send(first);
        }
        for _ in lines {}
    });
    match rx.recv_timeout(Duration::from_secs(30)) {
        Ok(url) if url.starts_with("http") => Ok((child, url.trim().to_string())),
        Ok(other) => {
            let _ = child.kill();
            Err(format!("rag.exe から想定外の応答がありました: {other}"))
        }
        Err(_) => {
            let _ = child.kill();
            Err("rag.exe が起動しませんでした（30秒以内に応答がありません）。セキュリティソフトでブロックされていないか確認してください。".into())
        }
    }
}

/// JavaScript の文字列リテラルにする（英数字以外は \\uXXXX にして安全に埋め込む）
fn js_string(s: &str) -> String {
    let mut out = String::from("\"");
    for u in s.encode_utf16() {
        let c = u as u32;
        if (c >= 0x30 && c <= 0x39) || (c >= 0x41 && c <= 0x5a) || (c >= 0x61 && c <= 0x7a) || c == 0x20 {
            out.push(char::from_u32(c).unwrap());
        } else {
            out.push_str(&format!("\\u{:04x}", c));
        }
    }
    out.push('"');
    out
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let window = match start_backend() {
                Ok((child, url)) => {
                    app.manage(Backend(Mutex::new(Some(child))));
                    let target = url.parse().map_err(|e| format!("URL が不正です: {e}"))?;
                    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(target))
                }
                Err(msg) => {
                    app.manage(Backend(Mutex::new(None)));
                    // 起動に失敗したときは理由を画面に出す
                    WebviewWindowBuilder::new(app, "main", WebviewUrl::App("error.html".into()))
                        .initialization_script(&format!("window.__RAG_ERROR = {};", js_string(&msg)))
                }
            };
            window
                .title("RAG プロンプトビルダー")
                .inner_size(1280.0, 900.0)
                .min_inner_size(800.0, 600.0)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("アプリを起動できませんでした")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app.try_state::<Backend>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
