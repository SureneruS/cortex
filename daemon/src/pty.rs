use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use std::io::{Read, Write};
use std::sync::Arc;
use tokio::sync::broadcast;
use tokio::task;

pub struct PtySession {
    writer: Arc<std::sync::Mutex<Box<dyn Write + Send>>>,
    pub output_tx: broadcast::Sender<Vec<u8>>,
    child: Arc<std::sync::Mutex<Box<dyn portable_pty::Child + Send>>>,
    _reader_handle: task::JoinHandle<()>,
}

impl PtySession {
    pub fn spawn(
        command: &str,
        args: &[&str],
        cwd: &str,
        env_vars: &[(String, String)],
        cols: u16,
        rows: u16,
    ) -> anyhow::Result<Self> {
        let pty_system = native_pty_system();

        let pair = pty_system.openpty(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })?;

        let mut cmd = CommandBuilder::new(command);
        for arg in args {
            cmd.arg(arg);
        }
        cmd.cwd(cwd);
        for (key, val) in env_vars {
            cmd.env(key, val);
        }

        let child = pair.slave.spawn_command(cmd)?;
        drop(pair.slave);

        let (output_tx, _) = broadcast::channel::<Vec<u8>>(256);

        let mut reader = pair.master.try_clone_reader()?;
        let tx = output_tx.clone();
        let reader_handle = task::spawn_blocking(move || {
            let mut buf = [0u8; 4096];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        let _ = tx.send(buf[..n].to_vec());
                    }
                    Err(_) => break,
                }
            }
        });

        let writer = pair.master.take_writer()?;

        Ok(PtySession {
            writer: Arc::new(std::sync::Mutex::new(writer)),
            output_tx,
            child: Arc::new(std::sync::Mutex::new(child)),
            _reader_handle: reader_handle,
        })
    }

    pub fn write(&self, data: &[u8]) -> anyhow::Result<()> {
        let mut w = self.writer.lock().unwrap();
        w.write_all(data)?;
        w.flush()?;
        Ok(())
    }

    pub fn resize(&self, _cols: u16, _rows: u16) -> anyhow::Result<()> {
        // portable-pty doesn't expose resize on MasterPty directly after creation.
        // We'd need to keep a handle to the pair. For now, this is a no-op.
        // TODO: implement resize via stored pty pair reference
        Ok(())
    }

    pub fn kill(&self) -> anyhow::Result<()> {
        let mut child = self.child.lock().unwrap();
        child.kill()?;
        Ok(())
    }

    #[allow(dead_code)]
    pub fn try_wait(&self) -> anyhow::Result<Option<portable_pty::ExitStatus>> {
        let mut child = self.child.lock().unwrap();
        Ok(child.try_wait()?)
    }
}
