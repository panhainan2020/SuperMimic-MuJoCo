/* Optional public media configuration. Never put tokens or signed private URLs here.
 * Overrides permit publishing selected clips only. With an empty baseUrl,
 * missing keys remain unavailable. Media is fetched only when a visitor plays.
 */
window.MEDIA_CONFIG = {
  enabled: true,
  baseUrl: "",
  overrides: {
    "lafan/overview.mp4": "https://supermimic-mujoco-results.zippyaspen7.chatgpt.site/media/lafan/overview.mp4",
    "100style/ood_low.mp4": "https://supermimic-mujoco-results.zippyaspen7.chatgpt.site/media/100style/ood_low.mp4",
    "100style/ood_median.mp4": "https://supermimic-mujoco-results.zippyaspen7.chatgpt.site/media/100style/ood_median.mp4",
    "100style/ood_high.mp4": "https://supermimic-mujoco-results.zippyaspen7.chatgpt.site/media/100style/ood_high.mp4",
    "100style/ood_failure.mp4": "https://supermimic-mujoco-results.zippyaspen7.chatgpt.site/media/100style/ood_failure.mp4"
  },
  repositoryUrl: "https://github.com/panhainan2020/SuperMimic-MuJoCo"
};
