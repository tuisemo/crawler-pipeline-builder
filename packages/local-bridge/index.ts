import puppeteer from 'puppeteer-core';
import WebSocket from 'ws';
import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs';

// Constants
const AGENT_ID = process.argv[2] || 'test_agent';
const SERVER_URL = process.argv[3] || 'ws://127.0.0.1:3100'; // Default to backend port
const TEMP_PROFILE_DIR = path.join(os.tmpdir(), `sea_temp_profile_${AGENT_ID}`);

function getChromePath(): string {
    switch (os.platform()) {
        case 'win32':
            return 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
        case 'darwin':
            return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
        case 'linux':
            return '/usr/bin/google-chrome';
        default:
            throw new Error('Unsupported platform: ' + os.platform());
    }
}

async function startBridge() {
    console.log(`Starting Sea Data Local Bridge...`);
    console.log(`Agent ID: ${AGENT_ID}`);
    console.log(`Target Server: ${SERVER_URL}`);

    // 1. Launch local browser with empty profile
    let browser: puppeteer.Browser;
    try {
        const chromePath = getChromePath();
        if (!fs.existsSync(chromePath)) {
            console.error(`Chrome executable not found at ${chromePath}. Please install Google Chrome or update the path.`);
            process.exit(1);
        }

        browser = await puppeteer.launch({
            executablePath: chromePath,
            headless: false,
            args: [
                '--remote-debugging-port=0',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-blink-features=AutomationControlled'
            ],
            userDataDir: TEMP_PROFILE_DIR,
            defaultViewport: null
        });
    } catch (error) {
        console.error('Failed to launch Chrome:', error);
        process.exit(1);
    }

    const browserWsEndpoint = browser.wsEndpoint();
    console.log(`✅ Local browser started. CDP Endpoint: ${browserWsEndpoint}`);

    // 2. Connect to local browser CDP
    const localWs = new WebSocket(browserWsEndpoint, { perMessageDeflate: false });

    localWs.on('open', () => {
        console.log('✅ Connected to local Chrome CDP.');
        connectToRelay(localWs);
    });

    localWs.on('error', (err) => {
        console.error('Local CDP WebSocket error:', err);
    });

    localWs.on('close', () => {
        console.log('Local Chrome was closed. Exiting...');
        process.exit(0);
    });
}

function connectToRelay(localWs: WebSocket) {
    const relayUrl = `${SERVER_URL}/api/relay/agent/${AGENT_ID}`;
    console.log(`Connecting to Cloud Relay: ${relayUrl}...`);
    
    // Disable deflate to avoid large payload decompression issues on proxy
    const cloudWs = new WebSocket(relayUrl, { perMessageDeflate: false });

    cloudWs.on('open', () => {
        console.log(`✅ Bridge successfully established! Waiting for workflows...`);
    });

    // Bi-directional forward
    cloudWs.on('message', (data, isBinary) => {
        if (localWs.readyState === WebSocket.OPEN) {
            localWs.send(data, { binary: isBinary });
        }
    });

    localWs.on('message', (data, isBinary) => {
        if (cloudWs.readyState === WebSocket.OPEN) {
            cloudWs.send(data, { binary: isBinary });
        }
    });

    cloudWs.on('close', () => {
        console.log('❌ Disconnected from Cloud Relay. Reconnecting in 3s...');
        setTimeout(() => connectToRelay(localWs), 3000);
    });

    cloudWs.on('error', (err) => {
        console.error('Cloud Relay WebSocket error:', err.message);
    });
}

// Start the bridge
startBridge().catch(console.error);
