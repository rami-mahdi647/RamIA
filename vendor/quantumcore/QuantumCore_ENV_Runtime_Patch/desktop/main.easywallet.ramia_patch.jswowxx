// main.easywallet.ramia_patch.js
//
// This file does NOT modify main.easywallet.full.js.
// It loads it and monkey-patches tx sending functions (BTC + ETH) to apply RamIA policies:
// - anti-spam scoring -> warnings + reasons + suggestions
// - fee penalties -> feeRate bump (BTC) / gas bump (ETH)
// - hard deny for extreme spam
//
// Run with: electron main.easywallet.ramia_patch.js
//
// Requires RamIA Policy Sidecar running:
//   python3 ~/RamIA/ramia_policy_service.py --host 127.0.0.1 --port 8787

const path = require("path");
const { txPolicy, POLICY_URL } = require("./ramia_policy_bridge");

// Load original main
const ORIGINAL_MAIN = path.join(__dirname, "main.easywallet.full.js");

// Helper: pretty log
function logPolicy(tag, info) {
  console.log(`[RamIA Policy] ${tag}:`, JSON.stringify(info, null, 2));
}

// Patch BTC Send by wrapping global function if it exists
function patchGlobal(name, wrapper) {
  const g = global;
  if (typeof g[name] === "function") {
    const orig = g[name];
    g[name] = wrapper(orig);
    console.log(`[RamIA Patch] patched global.${name}()`);
    return true;
  }
  return false;
}

// Patch function inside module scope:
// main.easywallet.full.js defines functions in its module scope, not globals.
// To patch without editing the file, we rely on a trick:
// - require() the original module
// - if it exports functions, patch exports
// If it doesn't export, then we patch by intercepting wallet.sendTransaction via ethers wrapper (global require cache).

function tryPatchExports(mod) {
  let patched = 0;

  // If module exports btcSend, patch it.
  if (mod && typeof mod.btcSend === "function") {
    const orig = mod.btcSend;
    mod.btcSend = async function patchedBtcSend(args, env) {
      // args: { index, to, amountSats, feeRate }
      const feeRate = args?.feeRate ?? 15;
      const amountSats = args?.amountSats ?? 0;
      const outputs = 2; // approx; wallet tx uses outputs + change
      const memo = "";   // btc send likely no memo

      const policy = await txPolicy({
        amount: amountSats,
        fee: Math.ceil(200 * feeRate), // rough pre-estimate; real fee computed later
        outputs,
        memo,
        to_addr: args?.to || "",
      });

      logPolicy("BTC tx_policy", policy);

      if (!policy.ok) {
        throw new Error(`RamIA Policy: transaction denied. reasons=${policy.reasons.join(",")}`);
      }

      // Apply fee multiplier as feeRate bump
      const mult = policy.fee_multiplier || 1.0;
      const bumpedFeeRate = Math.ceil(feeRate * mult);

      if (mult > 1.0) {
        console.log(`[RamIA Patch] BTC feeRate bumped ${feeRate} -> ${bumpedFeeRate}`);
        console.log(`[RamIA Patch] reasons: ${policy.reasons.join(", ")}`);
        console.log(`[RamIA Patch] suggestions: ${policy.suggestions.join(" | ")}`);
      }

      return await orig({ ...args, feeRate: bumpedFeeRate }, env);
    };
    patched += 1;
  }

  // If module exports init/wallet send hooks, we can patch similarly.
  return patched;
}

// Patch ETH sendTransaction: we patch ethers Wallet.prototype.sendTransaction
function patchEthersSendTransaction() {
  try {
    const ethers = require("ethers");
    if (!ethers?.Wallet?.prototype?.sendTransaction) return false;

    const orig = ethers.Wallet.prototype.sendTransaction;

    ethers.Wallet.prototype.sendTransaction = async function patchedSendTransaction(tx) {
      // tx: { to, value, gasPrice/maxFeePerGas, gasLimit, data }
      const to = tx?.to || "";
      const valueWei = tx?.value ? BigInt(tx.value.toString()) : 0n;
      const amountEth = Number(valueWei) / 1e18;

      // Estimate fee if provided; else use 0 and policy may bump
      let feeGuess = 0;
      try {
        if (tx?.gasLimit && (tx?.gasPrice || tx?.maxFeePerGas)) {
          const gasLimit = BigInt(tx.gasLimit.toString());
          const gp = BigInt((tx.gasPrice || tx.maxFeePerGas).toString());
          feeGuess = Number(gasLimit * gp);
        }
      } catch {}

      const memo = ""; // EVM memo not typical unless data
      const policy = await txPolicy({
        amount: amountEth,
        fee: feeGuess,
        outputs: 1,
        memo,
        to_addr: to,
      });

      logPolicy("ETH tx_policy", policy);

      if (!policy.ok) {
        throw new Error(`RamIA Policy: transaction denied. reasons=${policy.reasons.join(",")}`);
      }

      const mult = policy.fee_multiplier || 1.0;
      if (mult > 1.0) {
        console.log(`[RamIA Patch] ETH fee multiplier=${mult} reasons=${policy.reasons.join(", ")}`);
        console.log(`[RamIA Patch] suggestions: ${policy.suggestions.join(" | ")}`);

        // Bump gas price / maxFeePerGas
        try {
          if (tx.gasPrice) tx.gasPrice = BigInt(tx.gasPrice.toString()) * BigInt(Math.ceil(mult));
          if (tx.maxFeePerGas) tx.maxFeePerGas = BigInt(tx.maxFeePerGas.toString()) * BigInt(Math.ceil(mult));
          if (tx.maxPriorityFeePerGas) tx.maxPriorityFeePerGas = BigInt(tx.maxPriorityFeePerGas.toString()) * BigInt(Math.ceil(mult));
        } catch {}
      }

      return await orig.call(this, tx);
    };

    console.log("[RamIA Patch] patched ethers.Wallet.prototype.sendTransaction()");
    return true;
  } catch (e) {
    console.log("[RamIA Patch] ethers patch skipped:", e.message);
    return false;
  }
}

// Boot: run original main file then patch
(async function boot() {
  console.log("[RamIA Patch] Starting QuantumCore with RamIA Policy Sidecar:", POLICY_URL);

  // 1) Load original main (it will register electron IPC etc.)
  const mod = require(ORIGINAL_MAIN);

  // 2) Try patch exported functions (if any)
  const n = tryPatchExports(mod);
  console.log("[RamIA Patch] export patches:", n);

  // 3) Patch ethers sendTransaction (covers many flows)
  patchEthersSendTransaction();

  // 4) If btcSend exists globally (unlikely), patch it
  patchGlobal("btcSend", (orig) => async (args, env) => {
    const policy = await txPolicy({
      amount: args?.amountSats || 0,
      fee: 0,
      outputs: 2,
      memo: "",
      to_addr: args?.to || "",
    });
    if (!policy.ok) throw new Error(`Denied: ${policy.reasons.join(",")}`);
    const mult = policy.fee_multiplier || 1.0;
    return await orig({ ...args, feeRate: Math.ceil((args?.feeRate || 15) * mult) }, env);
  });

  console.log("[RamIA Patch] Boot complete.");
})();
