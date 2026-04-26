const https = require('https');

// URLs atualizadas com base na sua imagem do Railway
const targets = [
    { name: "API (ETI SENTINEL)", url: "https://monitoring-system-production-1e5a.up.railway.app/auth/status" },
    { name: "Frontend Correto (powerful-unity)", url: "https://powerful-unity-production.up.railway.app/" }
];

function check(target) {
    console.log(`🔍 Testando ${target.name}: ${target.url}`);
    const start = Date.now();
    
    const req = https.get(target.url, (res) => {
        const duration = Date.now() - start;
        if (res.statusCode === 200) {
            console.log(`✅ ${target.name}: ONLINE (200) - ${duration}ms`);
        } else {
            console.log(`❌ ${target.name}: ERRO ${res.statusCode}`);
        }
    });

    req.on('error', (e) => {
        console.log(`❌ ${target.name}: FALHA CRÍTICA (${e.message})`);
    });

    req.end();
}

console.log("=".repeat(50));
console.log("🚀 ETI SENTINEL - Scanner de Serviços Railway");
console.log("=".repeat(50));

targets.forEach((t, i) => {
    setTimeout(() => check(t), i * 1000);
});
