use clap::{Parser, Subcommand};

mod ipc;
mod pty;
mod session;

#[derive(Parser)]
#[command(name = "nova-daemon", about = "Nova PTY daemon")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Start the daemon (foreground)
    Start,
    /// Stop a running daemon
    Stop,
    /// Install as launchd service
    Install,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("nova_daemon=info".parse().unwrap()),
        )
        .init();

    let cli = Cli::parse();

    match cli.command {
        Commands::Start => {
            tracing::info!(
                "nova-daemon v{} (built {})",
                env!("CARGO_PKG_VERSION"),
                env!("BUILD_ID"),
            );
            if let Err(e) = ipc::serve().await {
                tracing::error!("Daemon error: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Stop => {
            tracing::info!("Stopping nova-daemon...");
            // TODO: send shutdown signal via PID file
        }
        Commands::Install => {
            tracing::info!("Installing launchd service...");
            // TODO: install plist
        }
    }
}
