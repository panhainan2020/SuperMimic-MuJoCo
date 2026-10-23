#!/usr/bin/env python3
"""Verify the static results site with an already-installed Playwright browser.

No browser downloads, remote artifact transfers, uploads or training. Optional
media checks stream existing local videos over a temporary loopback HTTP server.
Large training artifacts remain on server persistent storage.
"""
import argparse
import functools
import http.server
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--experiment-dir", type=Path)
    parser.add_argument("--screenshot-dir", type=Path)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    result = {"schema_version": 1, "mode": "static_and_optional_local_media", "checks": {}}
    with tempfile.TemporaryDirectory(prefix="supermimic-site-qa-") as tmp:
        target = Path(tmp)
        subprocess.run([sys.executable, str(HERE / "build.py"), "--output-dir", str(target)], check=True, capture_output=True)
        (target / "media-config.js").write_text('window.MEDIA_CONFIG = {enabled: false, overrides: {}, baseUrl: "", repositoryUrl: ""};\n')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(args.browser), headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors, network = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: network.append(request.url) if request.url.startswith(("http:", "https:")) else None)
            page.goto((target / "index.html").as_uri())
            page.wait_for_selector("#style-table tr")
            assert page.locator("#clip-table tr").count() == 40
            assert page.locator("#style-table tr").count() == 100
            assert page.locator("#comparison-table tbody tr").count() == 5
            assert page.locator("#media-unavailable").is_visible()
            assert page.locator("video[src]").count() == 0
            assert page.locator(".ood-media video").count() == 0
            assert not network, network
            result["checks"]["unconfigured_zero_network_and_no_invalid_players"] = True
            page.locator("#clip-search").fill("dance1_subject2")
            assert page.locator("#clip-table tr").count() == 1
            page.locator("#clip-search").fill("")
            page.locator("#category-filter").select_option("walk")
            assert page.locator("#clip-table tr").count() == 12
            page.locator("#category-filter").select_option("all")
            page.locator("#sort-order").select_option("return-desc")
            returns = [float(x) for x in page.locator("#clip-table .return-cell").all_text_contents()]
            assert returns == sorted(returns, reverse=True)
            page.locator("#style-search").fill("Flapping")
            assert page.locator("#style-table tr").count() == 1
            page.locator("#style-search").fill("")
            page.locator("#style-sort").select_option("failed-desc")
            assert "LimpLeft" in page.locator("#style-table tr").first.inner_text()
            result["checks"]["counts_search_filter_sort"] = True
            for href in page.locator("a[href]").evaluate_all("els => els.map(el => el.getAttribute('href'))"):
                if href.startswith(("https:", "http:", "#")):
                    continue
                assert (target / href).resolve().is_file(), href
            result["checks"]["local_result_links"] = True
            if args.screenshot_dir:
                args.screenshot_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(args.screenshot_dir / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile horizontal overflow"
            if args.screenshot_dir:
                page.screenshot(path=str(args.screenshot_dir / "mobile.png"), full_page=True)
            result["checks"]["mobile_390px_no_overflow"] = True
            if args.experiment_dir:
                media = json.loads((target / "results/098000/media_manifest.json").read_text())["videos"]
                selected = [x for x in media if x["key"] == "lafan/overview.mp4" or x["key"].startswith("100style/")]
                file_map = {"/media/" + x["key"]: args.experiment_dir / x["source_relative_path"] for x in selected}
                class Handler(http.server.SimpleHTTPRequestHandler):
                    def log_message(self, *unused):
                        pass
                    def copyfile(self, source, outputfile):
                        try:
                            super().copyfile(source, outputfile)
                        except (BrokenPipeError, ConnectionResetError):
                            # A paused/replaced video may cancel its loopback request.
                            pass
                    def translate_path(self, path):
                        key = unquote(urlparse(path).path)
                        if key in file_map:
                            return str(file_map[key])
                        return super().translate_path(path)
                handler = functools.partial(Handler, directory=str(target))
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
                server.daemon_threads = True
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    origin = "http://127.0.0.1:" + str(server.server_port)
                    config = {"enabled": True, "baseUrl": "", "overrides": {x["key"]: origin + "/media/" + x["key"] for x in selected}, "repositoryUrl": ""}
                    (target / "media-config.js").write_text("window.MEDIA_CONFIG = " + json.dumps(config) + ";\n")
                    network.clear()
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.goto(origin + "/index.html")
                    page.wait_for_selector(".ood-media video")
                    assert not [url for url in network if "/media/" in url]
                    page.locator("#play-video").click()
                    page.wait_for_function("document.querySelector('#main-video').currentTime > 0.05")
                    assert abs(page.locator("#main-video").evaluate("v => v.duration") - 70) < .1
                    page.locator("#main-video").evaluate("v => v.pause()")
                    # Only selected media are configured; seven full LAFAN slots are unavailable.
                    page.locator(".video-option").nth(1).click()
                    assert page.locator("#media-unavailable").is_visible()
                    assert not page.locator("#main-video").get_attribute("src")
                    durations = []
                    for i in range(4):
                        button = page.locator(".ood-media-item").nth(i).locator("button")
                        button.click()
                        page.wait_for_function("i => document.querySelectorAll('.ood-media video')[i].currentTime > 0.05", arg=i)
                        player = page.locator(".ood-media video").nth(i)
                        durations.append(player.evaluate("v => v.duration"))
                        assert page.locator("video").evaluate_all("els => els.filter(v => !v.paused).length") <= 1
                        player.evaluate("v => v.pause()")
                    assert all(abs(a - b) < .1 for a, b in zip(durations, [19.98, 19.98, 19.98, 17.76]))
                    result["checks"]["five_local_videos_play_and_partial_overrides"] = True
                    result["checks"]["zero_media_requests_before_click"] = True
                    if args.screenshot_dir:
                        page.locator("#ood").scroll_into_view_if_needed()
                        page.screenshot(path=str(args.screenshot_dir / "ood.png"), full_page=False)
                finally:
                    server.shutdown()
                    server.server_close()
            assert not errors, errors
            result["checks"]["javascript_errors"] = 0
            browser.close()
    result["passed"] = True
    (HERE / "qa.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
