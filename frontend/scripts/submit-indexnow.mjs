// @author wanghaobo
// 部署后向 IndexNow 提交 canonical URL（Bing 等参与方；非 Google 通道）。
// 用法：INDEXNOW_KEY=... HOST=oioi.bio node scripts/submit-indexnow.mjs [url...]
// 密钥与验证文件由运维配置，不入库。

const key = process.env.INDEXNOW_KEY?.trim();
const host = (process.env.HOST || "oioi.bio").trim();
const keyLocation = process.env.INDEXNOW_KEY_LOCATION?.trim() || `https://${host}/${key}.txt`;

if (!key) {
  console.error("submit-indexnow: set INDEXNOW_KEY");
  process.exit(1);
}

const urls =
  process.argv.slice(2).length > 0
    ? process.argv.slice(2)
    : [
        `https://${host}/`,
        `https://${host}/zh`,
        `https://${host}/en/novel-to-video`,
        `https://${host}/zh/novel-to-video`,
        `https://${host}/en/ai-storyboard-generator`,
        `https://${host}/zh/ai-storyboard-generator`,
      ];

const body = {
  host,
  key,
  keyLocation,
  urlList: urls,
};

const response = await fetch("https://api.indexnow.org/indexnow", {
  method: "POST",
  headers: { "content-type": "application/json; charset=utf-8" },
  body: JSON.stringify(body),
});

const text = await response.text();
console.log(`submit-indexnow: ${response.status} ${text || "(empty)"}`);
if (!response.ok) process.exit(1);
