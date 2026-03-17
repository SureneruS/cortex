fn main() {
    let now = chrono::Utc::now().format("%Y%m%d.%H%M%S").to_string();
    println!("cargo:rustc-env=BUILD_ID={}", now);
    // Rebuild when any source changes
    println!("cargo:rerun-if-changed=src/");
}
