class ZcodeSupervisor < Formula
  desc "Codex-side supervisor tooling for bounded ZCode delegation"
  homepage "https://github.com/AkiGarage/ZCode-supervisor"
  url "https://github.com/AkiGarage/homebrew-zcode-supervisor/releases/download/v0.0.2/zcode-supervisor-v0.0.2.tar.gz"
  sha256 "0e8ecf32765bbcaeb3529b760485620088bc7f4eafc1e802a29a2077de66a9e0"
  license "MIT"

  depends_on "git"
  depends_on "node@22"
  depends_on "python@3.11"

  def install
    libexec.install Dir["*"]

    python = Formula["python@3.11"].opt_libexec/"bin/python3"
    node_path = Formula["node@22"].opt_bin
    python_path = Formula["python@3.11"].opt_libexec/"bin"

    {
      "zcode-install-repo"  => "#{libexec}/scripts/zcode-install-repo",
      "zcode-auto-route"    => "#{libexec}/scripts/zcode-auto-route",
      "zcode-supervisor"    => "#{libexec}/tools/zcode_supervisor/zcode_supervisor.py",
      "zcode-eval"          => "#{libexec}/tools/zcode_eval/zcode_eval.py",
      "zcode-release-check" => "#{libexec}/tools/zcode_eval/zcode_release.py",
    }.each do |command, target|
      wrapper = bin/command
      wrapper.write <<~EOS
        #!/bin/bash
        export PATH="#{node_path}:#{python_path}:$PATH"
        exec "#{python}" "#{target}" "$@"
      EOS
      wrapper.chmod 0755
    end
  end

  test do
    target = testpath/"target"
    target.mkpath
    system "git", "init", target

    system bin/"zcode-install-repo", target
    assert_path_exists target/".codex/zcode-routing.json"
    assert_path_exists target/".codex/ZCODE_DELEGATION.md"
    assert_path_exists target/".agents/mcp.json"
    assert_path_exists target/"AGENTS.md"

    route = shell_output("#{bin}/zcode-auto-route --workspace #{target} --objective 'fix src/app.js'")
    assert_match "needs_codex_planning", route

    system bin/"zcode-supervisor", "--help"
    system bin/"zcode-eval", "--help"
    system bin/"zcode-release-check", "--help"
  end
end
