use crate::pty::PtySession;
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionState {
    pub repos: Vec<String>,
    pub transcript_path: String,
    pub memory_injected: bool,
    pub goal: Option<String>,
    pub started_at: String,
    pub last_active_at: String,
    pub tmux_target: Option<String>,
    pub tmux_window: Option<String>,
    pub slack_thread_ts: Option<String>,
    pub slack_channel: Option<String>,
    pub chain_id: Option<String>,
    pub chain_sequence: i32,
    pub parent_session_id: Option<String>,
    pub compaction_count: i32,
    pub status: String,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub permission_mode: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NovaStateFile {
    pub last_dream_run: Option<String>,
    pub sessions: HashMap<String, SessionState>,
    #[serde(default)]
    pub slack: HashMap<String, String>,
}

pub struct SessionInfo {
    pub id: Uuid,
    pub name: String,
    pub state: SessionState,
    pub pty: PtySession,
}

pub struct SessionManager {
    pub sessions: HashMap<Uuid, SessionInfo>,
    state_path: PathBuf,
}

impl SessionManager {
    pub fn new() -> Self {
        let home = dirs_path();
        let state_path = home.join("state.json");
        SessionManager {
            sessions: HashMap::new(),
            state_path,
        }
    }

    pub fn create_session(
        &mut self,
        name: String,
        cwd: String,
        repos: Vec<String>,
        tags: Vec<String>,
        prompt: String,
        permission_mode: String,
    ) -> anyhow::Result<Uuid> {
        let id = Uuid::new_v4();
        let now = Utc::now().to_rfc3339();

        let mode = if permission_mode.is_empty() {
            "default"
        } else {
            &permission_mode
        };
        let args = vec![format!("--permission-mode={}", mode)];
        let args_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();

        let mut env_vars = vec![
            ("NOVA_SESSION_ID".to_string(), id.to_string()),
            ("NOVA_SESSION_NAME".to_string(), name.clone()),
        ];
        for repo in &repos {
            env_vars.push(("NOVA_REPOS".to_string(), repo.clone()));
        }

        let pty = PtySession::spawn("claude", &args_refs, &cwd, &env_vars, 120, 40)?;

        if !prompt.is_empty() {
            let prompt_bytes = format!("{}\n", prompt);
            let pty_ref = &pty;
            // Brief delay to let the process start, then send prompt
            std::thread::sleep(std::time::Duration::from_millis(500));
            let _ = pty_ref.write(prompt_bytes.as_bytes());
        }

        let state = SessionState {
            repos,
            transcript_path: String::new(),
            memory_injected: false,
            goal: None,
            started_at: now.clone(),
            last_active_at: now,
            tmux_target: None,
            tmux_window: None,
            slack_thread_ts: None,
            slack_channel: None,
            chain_id: None,
            chain_sequence: 0,
            parent_session_id: None,
            compaction_count: 0,
            status: "active".to_string(),
            tags,
            name: name.clone(),
            permission_mode,
        };

        self.sessions.insert(
            id,
            SessionInfo {
                id,
                name,
                state: state.clone(),
                pty,
            },
        );

        self.save_state()?;
        Ok(id)
    }

    pub fn kill_session(&mut self, id: Uuid) -> anyhow::Result<()> {
        if let Some(info) = self.sessions.get(&id) {
            info.pty.kill()?;
        }
        if let Some(info) = self.sessions.get_mut(&id) {
            info.state.status = "completed".to_string();
        }
        self.save_state()?;
        Ok(())
    }

    pub fn list_sessions(&self) -> Vec<SessionListItem> {
        self.sessions
            .values()
            .map(|info| SessionListItem {
                id: info.id,
                name: info.name.clone(),
                status: info.state.status.clone(),
                repos: info.state.repos.clone(),
                tags: info.state.tags.clone(),
                started_at: info.state.started_at.clone(),
                last_active_at: info.state.last_active_at.clone(),
            })
            .collect()
    }

    fn save_state(&self) -> anyhow::Result<()> {
        let mut sessions = HashMap::new();
        for (id, info) in &self.sessions {
            sessions.insert(id.to_string(), info.state.clone());
        }

        // Read existing state to preserve fields we don't manage
        let existing: NovaStateFile = if self.state_path.exists() {
            let data = std::fs::read_to_string(&self.state_path)?;
            serde_json::from_str(&data).unwrap_or(NovaStateFile {
                last_dream_run: None,
                sessions: HashMap::new(),
                slack: HashMap::new(),
            })
        } else {
            NovaStateFile {
                last_dream_run: None,
                sessions: HashMap::new(),
                slack: HashMap::new(),
            }
        };

        let state_file = NovaStateFile {
            last_dream_run: existing.last_dream_run,
            sessions,
            slack: existing.slack,
        };

        let json = serde_json::to_string_pretty(&state_file)?;
        let tmp_path = self.state_path.with_extension("tmp");
        std::fs::write(&tmp_path, &json)?;
        std::fs::rename(&tmp_path, &self.state_path)?;
        Ok(())
    }
}

#[derive(Debug, Serialize)]
pub struct SessionListItem {
    pub id: Uuid,
    pub name: String,
    pub status: String,
    pub repos: Vec<String>,
    pub tags: Vec<String>,
    pub started_at: String,
    pub last_active_at: String,
}

fn dirs_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    PathBuf::from(home).join(".nova")
}
