// src/index.js
export default {
	async fetch(request, env) {
	  const url = new URL(request.url);
	  const json = (obj, code=200, extra={}) =>
		new Response(JSON.stringify(obj), {
		  status: code,
		  headers: { "content-type": "application/json", ...extra }
		});
  
	  // CORS / preflight (lets you test from anywhere)
	  if (request.method === "OPTIONS") {
		return new Response(null, {
		  headers: {
			"access-control-allow-origin": "*",
			"access-control-allow-methods": "GET,POST,OPTIONS",
			"access-control-allow-headers": "content-type"
		  }
		});
	  }
  
	  // --- POST /enqueue (TradingView sends here)
	  if (url.pathname === "/enqueue" && request.method === "POST") {
		let body;
		try { body = await request.json(); } catch (_) {
		  return json({ ok:false, error:"Invalid JSON" }, 400);
		}
  
		// Simple shared-secret check (TradingView can't set headers, so put token in body)
		if (env.WEBHOOK_SECRET && body.token !== env.WEBHOOK_SECRET) {
		  return json({ ok:false, error:"Bad token" }, 403);
		}
  
		const account = (body.account || "FTMO").toUpperCase();
		const key = `q:${account}`;
  
		// Add unique signal ID to prevent duplicates
		const signalId = Date.now() + "-" + Math.random().toString(36).substr(2, 9);
		
		const current = await env.QUEUE.get(key);
		const queue = current ? JSON.parse(current) : [];
		queue.push({ ...body, signalId, receivedAt: Date.now() });
  
		await env.QUEUE.put(key, JSON.stringify(queue));
		return json({ ok:true, size: queue.length, signalId }, 200, { "access-control-allow-origin": "*" });
	  }
  
	  // --- GET /dequeue?account=FTMO (MT5 EA polls this)
	  if (url.pathname === "/dequeue" && request.method === "GET") {
		const account = (url.searchParams.get("account") || "FTMO").toUpperCase();
		const key = `q:${account}`;
  
		try {
		  const current = await env.QUEUE.get(key);
		  const queue = current ? JSON.parse(current) : [];
		  const next = queue.shift() || null;
  
		  // Only update KV if we actually dequeued something (saves KV writes)
		  if (next) {
			await env.QUEUE.put(key, JSON.stringify(queue));
		  }
		  
		  return json(next, 200, { "access-control-allow-origin": "*" });
		} catch (error) {
		  // If KV fails (limit exceeded), return null gracefully
		  console.log("KV error:", error.message);
		  return json(null, 200, { "access-control-allow-origin": "*" });
		}
	  }
  
	  return new Response("Not found", { status: 404 });
	}
  };
  