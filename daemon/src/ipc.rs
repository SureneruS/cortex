use crate::session::SessionManager;
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixListener;
use tokio::sync::Mutex;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
#[serde(rename_all = "snake_case")]
#[allow(dead_code)]
enum Request {
    ListSessions,
    CreateSession {
        name: String,
        cwd: String,
        #[serde(default)]
        repos: Vec<String>,
        #[serde(default)]
        tags: Vec<String>,
        #[serde(default)]
        prompt: String,
        #[serde(default)]
        permission_mode: String,
    },
    KillSession {
        session_id: Uuid,
    },
    AttachPty {
        session_id: Uuid,
        #[serde(default = "default_cols")]
        cols: u16,
        #[serde(default = "default_rows")]
        rows: u16,
    },
    DetachPty {
        session_id: Uuid,
    },
    Input {
        session_id: Uuid,
        data: String, // base64
    },
    Resize {
        session_id: Uuid,
        cols: u16,
        rows: u16,
    },
}

fn default_cols() -> u16 {
    120
}
fn default_rows() -> u16 {
    40
}

#[derive(Debug, Serialize)]
#[serde(tag = "type")]
#[serde(rename_all = "snake_case")]
enum Response {
    Sessions {
        data: Vec<crate::session::SessionListItem>,
    },
    SessionCreated {
        session_id: Uuid,
    },
    SessionKilled {
        session_id: Uuid,
    },
    PtyOutput {
        session_id: Uuid,
        data: String, // base64
    },
    Attached {
        session_id: Uuid,
    },
    Detached {
        session_id: Uuid,
    },
    Error {
        message: String,
    },
}

pub async fn serve() -> anyhow::Result<()> {
    let socket_path = socket_path();
    // Remove stale socket
    let _ = std::fs::remove_file(&socket_path);
    // Ensure directory exists
    if let Some(parent) = socket_path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let listener = UnixListener::bind(&socket_path)?;
    tracing::info!("Listening on {}", socket_path.display());

    // Write PID file
    let pid_path = socket_path.with_file_name("nova-daemon.pid");
    std::fs::write(&pid_path, std::process::id().to_string())?;

    let manager = Arc::new(Mutex::new(SessionManager::new()));

    // Handle graceful shutdown
    let socket_path_clone = socket_path.clone();
    let pid_path_clone = pid_path.clone();
    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.ok();
        tracing::info!("Shutting down...");
        let _ = std::fs::remove_file(&socket_path_clone);
        let _ = std::fs::remove_file(&pid_path_clone);
        std::process::exit(0);
    });

    loop {
        let (stream, _) = listener.accept().await?;
        let manager = manager.clone();
        tokio::spawn(async move {
            if let Err(e) = handle_client(stream, manager).await {
                tracing::error!("Client error: {}", e);
            }
        });
    }
}

async fn handle_client(
    stream: tokio::net::UnixStream,
    manager: Arc<Mutex<SessionManager>>,
) -> anyhow::Result<()> {
    let (reader, writer) = stream.into_split();
    let mut lines = BufReader::new(reader).lines();
    let writer = Arc::new(Mutex::new(writer));

    while let Some(line) = lines.next_line().await? {
        let request: Request = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                tracing::warn!("Invalid request: {}", e);
                let resp = Response::Error {
                    message: format!("Invalid request: {}", e),
                };
                send_response(&writer, &resp).await?;
                continue;
            }
        };

        match request {
            Request::ListSessions => {
                let mgr = manager.lock().await;
                let items = mgr.list_sessions();
                tracing::info!("list_sessions → {} sessions", items.len());
                send_response(&writer, &Response::Sessions { data: items }).await?;
            }
            Request::CreateSession {
                name,
                cwd,
                repos,
                tags,
                prompt,
                permission_mode,
            } => {
                tracing::info!("create_session name={} cwd={}", name, cwd);
                let mut mgr = manager.lock().await;
                match mgr.create_session(name, cwd, repos, tags, prompt, permission_mode) {
                    Ok(id) => {
                        tracing::info!("session created: {}", id);
                        send_response(&writer, &Response::SessionCreated { session_id: id })
                            .await?;
                    }
                    Err(e) => {
                        tracing::error!("create_session failed: {}", e);
                        send_response(
                            &writer,
                            &Response::Error {
                                message: e.to_string(),
                            },
                        )
                        .await?;
                    }
                }
            }
            Request::KillSession { session_id } => {
                tracing::info!("kill_session {}", session_id);
                let mut mgr = manager.lock().await;
                match mgr.kill_session(session_id) {
                    Ok(()) => {
                        send_response(&writer, &Response::SessionKilled { session_id }).await?;
                    }
                    Err(e) => {
                        tracing::error!("kill_session failed: {}", e);
                        send_response(
                            &writer,
                            &Response::Error {
                                message: e.to_string(),
                            },
                        )
                        .await?;
                    }
                }
            }
            Request::AttachPty {
                session_id,
                cols: _,
                rows: _,
            } => {
                tracing::info!("attach_pty {}", session_id);
                let mgr = manager.lock().await;
                if let Some(info) = mgr.sessions.get(&session_id) {
                    let mut rx = info.pty.output_tx.subscribe();
                    let w = writer.clone();
                    let sid = session_id;
                    tokio::spawn(async move {
                        while let Ok(data) = rx.recv().await {
                            let encoded = BASE64.encode(&data);
                            let resp = Response::PtyOutput {
                                session_id: sid,
                                data: encoded,
                            };
                            if send_response(&w, &resp).await.is_err() {
                                break;
                            }
                        }
                    });
                    send_response(&writer, &Response::Attached { session_id }).await?;
                } else {
                    send_response(
                        &writer,
                        &Response::Error {
                            message: "Session not found".to_string(),
                        },
                    )
                    .await?;
                }
            }
            Request::DetachPty { session_id } => {
                // The streaming task will end when the broadcast receiver is dropped
                send_response(&writer, &Response::Detached { session_id }).await?;
            }
            Request::Input { session_id, data } => {
                let decoded = BASE64.decode(&data)?;
                let mgr = manager.lock().await;
                if let Some(info) = mgr.sessions.get(&session_id) {
                    info.pty.write(&decoded)?;
                }
            }
            Request::Resize {
                session_id,
                cols,
                rows,
            } => {
                let mgr = manager.lock().await;
                if let Some(info) = mgr.sessions.get(&session_id) {
                    let _ = info.pty.resize(cols, rows);
                }
            }
        }
    }
    Ok(())
}

async fn send_response(
    writer: &Arc<Mutex<tokio::net::unix::OwnedWriteHalf>>,
    resp: &Response,
) -> anyhow::Result<()> {
    let mut json = serde_json::to_string(resp)?;
    json.push('\n');
    let mut w = writer.lock().await;
    w.write_all(json.as_bytes()).await?;
    w.flush().await?;
    Ok(())
}

fn socket_path() -> std::path::PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    std::path::PathBuf::from(home)
        .join(".nova")
        .join("nova.sock")
}
