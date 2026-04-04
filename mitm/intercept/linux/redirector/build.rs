use aya_build::cargo_metadata;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cargo_metadata = cargo_metadata::MetadataCommand::new().no_deps().exec()?;
    let bpf_src = cargo_metadata
        .workspace_root
        .join("src/bpf/redirector.bpf.c");
    aya_build::build_ebpf([bpf_src])?;
    Ok(())
}
