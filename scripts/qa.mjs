import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const baseURL=process.env.QA_BASE_URL||'http://127.0.0.1:4775';
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
await page.goto(baseURL);
await page.locator('#loading').waitFor({state:'hidden',timeout:95000});
await page.waitForFunction(()=>document.querySelectorAll('#agent-dock button').length===6);
await fs.mkdir('qa',{recursive:true});await page.screenshot({path:'qa/office-desktop.png'});
for(const tab of ['science','research','meetings','launch','office']){await page.locator(`[data-tab="${tab}"]`).click();if(!(await page.locator('#panel-title').textContent()))throw Error('Empty tab '+tab);}
await page.locator('[data-agent="buzz"]').click();await page.waitForTimeout(800);await page.screenshot({path:'qa/agent-focus.png'});
await page.locator('#close-brain-modal').click();
await page.locator('#reset-camera').click();
await page.setViewportSize({width:390,height:844});await page.locator('#close-inspector').click();await page.screenshot({path:'qa/office-mobile.png'});
const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
console.log(JSON.stringify({errors,overflow,agents:await page.locator('#agent-dock button').count(),provider:await page.locator('#provider-chip').textContent()}));
await browser.close();if(errors.length||overflow)process.exitCode=1;
