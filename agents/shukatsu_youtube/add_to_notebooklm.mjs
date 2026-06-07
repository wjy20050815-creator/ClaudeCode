/**
 * NotebookLM への YouTube ソース追加スクリプト
 * patchright + 保存済み認証状態を使用
 *
 * Usage: node add_to_notebooklm.mjs [--screenshot-only]
 */

import pkg from "/Users/jiayi/.npm/_npx/0d29dd9f4e472da9/node_modules/patchright/index.js";
const { chromium } = pkg;
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const STATE_FILE = "/Users/jiayi/Library/Application Support/notebooklm-mcp/browser_state/state.json";
const SCREENSHOT_DIR = "/Users/jiayi/Developer/ClaudeCode/agents/shukatsu_youtube/screenshots";

const NOTEBOOKS = {
  "商社就活": {
    url: "https://notebooklm.google.com/notebook/8743728a-1fcc-443b-abfa-165d2f565d2b",
    videos: [
      { url: "https://www.youtube.com/watch?v=kNoZl4E8jG4", title: "【就活】総合商社はどのような学生が受かるのか？" },
    ]
  },
  "金融就活": {
    url: "https://notebooklm.google.com/notebook/032636c9-287e-47ec-b32c-f8b37b5844a8",
    videos: [
      { url: "https://www.youtube.com/watch?v=LqzDPRL76Wk", title: "投資銀行内定のための5つの条件" },
      { url: "https://www.youtube.com/watch?v=ZLEL3oXSEG4", title: "外銀内定者の特徴はここだ！" },
    ]
  },
  "全行業共通就活": {
    url: "https://notebooklm.google.com/notebook/c698f9d1-c9cf-4b85-a52f-40dec0cf4f34",
    videos: [
      { url: "https://www.youtube.com/watch?v=7IqjAgF4sFI", title: "これ見るだけで面接通過率アップ！神回答とNG回答" },
    ]
  }
};

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function takeScreenshot(page, name) {
  const { mkdirSync } = await import("fs");
  mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const path = join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path, fullPage: false });
  console.log(`  📸 ${path}`);
}

// Source picker is open when we can see the website/upload buttons
const PICKER_BTNS = [
  'button:has-text("网站")',
  'button:has-text("ウェブサイト")',
  'button:has-text("Website")',
  "button.drop-zone-icon-button",
  'button:has-text("上传文件")',
];

async function isPickerVisible(page) {
  for (const sel of PICKER_BTNS) {
    if (await page.locator(sel).first().isVisible({ timeout: 500 }).catch(() => false)) return true;
  }
  return false;
}

async function openPicker(page) {
  // Already open?
  if (await isPickerVisible(page)) return true;

  // Click sidebar "添加来源"
  const addBtns = [
    "button.add-source-button",
    '[aria-label="添加来源"]',
    '[aria-label*="Add source" i]',
    '[aria-label*="ソースを追加" i]',
  ];
  for (const sel of addBtns) {
    const btn = page.locator(sel).first();
    if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await btn.click({ force: true });
      await sleep(2000);
      return await isPickerVisible(page);
    }
  }
  return false;
}

async function addYouTubeSource(page, videoUrl, title, notebookName, index) {
  console.log(`\n  → 追加中: ${title}`);
  await sleep(2000);

  // 1. Open source picker
  if (!await openPicker(page)) {
    await takeScreenshot(page, `${notebookName}_${index}_no_picker`);
    console.log(`    ❌ ソースピッカーが開けません`);
    return false;
  }

  // 2. Click "网站" (Website / URL) button
  const websiteSels = [
    'button:has-text("网站")',
    'button:has-text("ウェブサイト")',
    'button:has-text("Website")',
    'button:has-text("Websites")',
    "button.drop-zone-icon-button:has(mat-icon.youtube-icon)",
    'button.drop-zone-icon-button:has(mat-icon:text-is("link"))',
  ];
  for (const sel of websiteSels) {
    const btn = page.locator(sel).first();
    if (await btn.isVisible({ timeout: 1500 }).catch(() => false)) {
      await btn.click();
      console.log(`    ✓ "网站" クリック`);
      await sleep(1000);
      break;
    }
  }

  // 3. Fill URL input
  const inputSels = [
    'input[type="url"]',
    'input[placeholder*="URL" i]',
    'input[placeholder*="http" i]',
    'input[type="text"]:not([readonly])',
    'textarea',
  ];
  let filled = false;
  for (const sel of inputSels) {
    const inp = page.locator(sel).first();
    if (await inp.isVisible({ timeout: 2000 }).catch(() => false)) {
      await inp.fill(videoUrl);
      console.log(`    ✓ URL 入力: ${videoUrl}`);
      filled = true;
      break;
    }
  }
  if (!filled) {
    await takeScreenshot(page, `${notebookName}_${index}_no_input`);
    console.log(`    ❌ URL 入力欄が見つかりません`);
    return false;
  }

  await sleep(600);

  // 4. Submit — "插入" button is in the source panel, NOT inside .cdk-overlay-container
  // Try page-level first, then Enter fallback
  const submitSels = [
    'button:has-text("插入")',  // Chinese "Insert"
    'button:has-text("挿入")',  // Japanese "Insert"
    'button:has-text("追加")',  // Japanese "Add"
    'button:has-text("Insert")',
    'button.mat-mdc-raised-button:not(.create-notebook-button)',
    'button.mdc-button--raised:not(.create-notebook-button)',
  ];
  for (const sel of submitSels) {
    const btn = page.locator(sel).first();
    if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
      if (await btn.isDisabled().catch(() => false)) continue;
      await btn.click({ force: true });
      console.log(`    ✓ 送信クリック (${sel})`);
      await sleep(12000);
      console.log(`    ✅ 完了: ${title}`);
      return true;
    }
  }

  // Last resort: press Enter in the input
  await page.keyboard.press("Enter");
  console.log(`    ✓ Enter キーで送信`);
  await sleep(12000);
  console.log(`    ✅ 完了 (Enter): ${title}`);
  return true;
}

async function main() {
  const screenshotOnly = process.argv.includes("--screenshot-only");

  if (!existsSync(STATE_FILE)) {
    console.error(`❌ ブラウザ状態ファイルが見つかりません: ${STATE_FILE}`);
    process.exit(1);
  }

  const storageState = JSON.parse(readFileSync(STATE_FILE, "utf-8"));

  console.log("🚀 NotebookLM ソース追加スクリプト起動");

  const browser = await chromium.launchPersistentContext(
    "/Users/jiayi/Library/Application Support/notebooklm-mcp/chrome_profile",
    {
      headless: false,
      executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      storageState,
      args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    }
  );

  const page = await browser.newPage();

  try {
    for (const [notebookName, { url: notebookUrl, videos }] of Object.entries(NOTEBOOKS)) {
      console.log(`\n📓 ノートブック: ${notebookName}`);

      await page.goto(notebookUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
      await sleep(3000);

      if (screenshotOnly) {
        await takeScreenshot(page, `${notebookName}_initial`);
        continue;
      }

      for (let i = 0; i < videos.length; i++) {
        const video = videos[i];
        // Re-navigate to notebook before each video to reset picker state
        await page.goto(notebookUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
        await sleep(3000);
        await addYouTubeSource(page, video.url, video.title, notebookName, i);
        await sleep(2000);
      }
    }

    console.log("\n✅ 全ノートブック処理完了");
  } finally {
    await browser.close();
  }
}

main().catch(e => {
  console.error("❌ エラー:", e);
  process.exit(1);
});
