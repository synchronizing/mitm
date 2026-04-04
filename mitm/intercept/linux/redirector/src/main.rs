use anyhow::{Context, Result};
use aya::programs::{CgroupSock, CgroupSockAttachType};
use aya::Bpf;
use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Write};
use tokio::signal;

#[derive(Deserialize, Debug)]
struct Config {
    tun_name: String,
    proxy_port: u16,
    target_process: String,
}

#[derive(Serialize)]
struct Status {
    status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    msg: Option<String>,
}

#[tokio::main]
async fn main() -> Result<()> {
    let stdin = std::io::stdin();
    let mut line = String::new();
    BufReader::new(stdin.lock()).read_line(&mut line)?;
    let config: Config = serde_json::from_str(line.trim())
        .context("Failed to parse config JSON from stdin")?;

    let bpf_bytes = include_bytes!(concat!(env!("OUT_DIR"), "/redirector.bpf.o"));
    let mut bpf = Bpf::load(bpf_bytes)?;

    let mut target_comm: aya::maps::Array<_, [u8; 16]> =
        aya::maps::Array::try_from(bpf.map_mut("target_comm")?)?;
    let mut name_bytes = [0u8; 16];
    let name = config.target_process.as_bytes();
    let len = name.len().min(15);
    name_bytes[..len].copy_from_slice(&name[..len]);
    target_comm.set(0, name_bytes, 0)?;

    let tun_config = tun::Configuration::default();
    let _tun = tun::create_as_async(&tun_config).context("Failed to create TUN device")?;

    let tun_ifindex: u32 = {
        let iface = nix::net::if_::if_nametoindex(config.tun_name.as_str())
            .unwrap_or(0);
        iface
    };

    let mut ifindex_map: aya::maps::Array<_, u32> =
        aya::maps::Array::try_from(bpf.map_mut("tun_ifindex")?)?;
    ifindex_map.set(0, tun_ifindex, 0)?;

    let cgroup = std::fs::File::open("/sys/fs/cgroup")
        .context("Failed to open /sys/fs/cgroup")?;
    let prog: &mut CgroupSock = bpf
        .program_mut("redirect_sock")
        .context("BPF program not found")?
        .try_into()?;
    prog.load()?;
    prog.attach(&cgroup, CgroupSockAttachType::SockCreate)?;

    let stdout = std::io::stdout();
    let mut out = stdout.lock();
    writeln!(out, "{}", serde_json::to_string(&Status { status: "ready".into(), msg: None })?)?;
    out.flush()?;

    signal::ctrl_c().await?;

    Ok(())
}
