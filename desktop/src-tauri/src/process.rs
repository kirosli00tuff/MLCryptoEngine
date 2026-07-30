//! Child process supervision for the Python recorder and telemetry services.

use std::collections::HashMap;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

const STOP_GRACE: Duration = Duration::from_secs(6);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProcKind {
    Recorder,
    Telemetry,
}

impl ProcKind {
    pub fn as_str(self) -> &'static str {
        match self {
            ProcKind::Recorder => "recorder",
            ProcKind::Telemetry => "telemetry",
        }
    }

    fn module(self) -> &'static str {
        match self {
            ProcKind::Recorder => "data.recorder",
            ProcKind::Telemetry => "ops.telemetry",
        }
    }

    const ALL: [ProcKind; 2] = [ProcKind::Recorder, ProcKind::Telemetry];
}

struct Managed {
    child: Child,
    started: Instant,
}

#[derive(Default)]
pub struct ProcessManager {
    procs: HashMap<ProcKind, Managed>,
}

#[derive(Serialize)]
pub struct ProcessStatus {
    pub kind: &'static str,
    pub running: bool,
    pub pid: Option<u32>,
    pub uptime_s: Option<u64>,
}

impl ProcessManager {
    /// Drop exited children so status and start() see reality.
    fn reap(&mut self) {
        self.procs
            .retain(|_, managed| matches!(managed.child.try_wait(), Ok(None)));
    }

    pub fn start(
        &mut self,
        repo_root: &Path,
        kind: ProcKind,
        venues: &[String],
    ) -> Result<u32, String> {
        self.reap();
        if self.procs.contains_key(&kind) {
            return Err(format!("{} is already running", kind.as_str()));
        }
        let mut cmd = Command::new("uv");
        cmd.arg("run")
            .arg("python")
            .arg("-m")
            .arg(kind.module())
            .current_dir(repo_root)
            // Services write structured logs to files themselves; the pipes
            // stay closed so a chatty child can never block on a full pipe.
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        if kind == ProcKind::Recorder {
            for venue in venues {
                cmd.arg("--venue").arg(venue);
            }
        }
        let child = cmd.spawn().map_err(|e| {
            format!(
                "failed to start {}: {e}. Is `uv` installed and on PATH?",
                kind.as_str()
            )
        })?;
        let pid = child.id();
        self.procs.insert(
            kind,
            Managed {
                child,
                started: Instant::now(),
            },
        );
        Ok(pid)
    }

    pub fn status(&mut self) -> Vec<ProcessStatus> {
        self.reap();
        ProcKind::ALL
            .iter()
            .map(|kind| match self.procs.get(kind) {
                Some(managed) => ProcessStatus {
                    kind: kind.as_str(),
                    running: true,
                    pid: Some(managed.child.id()),
                    uptime_s: Some(managed.started.elapsed().as_secs()),
                },
                None => ProcessStatus {
                    kind: kind.as_str(),
                    running: false,
                    pid: None,
                    uptime_s: None,
                },
            })
            .collect()
    }

    /// SIGTERM first so the service can flush its zstd frame and log a clean
    /// shutdown; SIGKILL only after the grace period.
    pub fn stop(&mut self, kind: ProcKind) -> Result<(), String> {
        let Some(mut managed) = self.procs.remove(&kind) else {
            return Ok(());
        };
        let pid = managed.child.id() as i32;
        unsafe {
            libc::kill(pid, libc::SIGTERM);
        }
        let deadline = Instant::now() + STOP_GRACE;
        loop {
            match managed.child.try_wait() {
                Ok(Some(_)) => return Ok(()),
                Ok(None) => {
                    if Instant::now() >= deadline {
                        let _ = managed.child.kill();
                        let _ = managed.child.wait();
                        return Ok(());
                    }
                    std::thread::sleep(Duration::from_millis(120));
                }
                Err(e) => return Err(format!("waiting for {}: {e}", kind.as_str())),
            }
        }
    }

    pub fn stop_all(&mut self) {
        for kind in ProcKind::ALL {
            let _ = self.stop(kind);
        }
    }
}
