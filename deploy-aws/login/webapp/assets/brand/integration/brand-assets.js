// Framework-neutral URLs. Import from the deployed brand directory.
const base = new URL("../", import.meta.url);
const asset = path => new URL(path, base).href;
export const ZMD_BRAND = Object.freeze({
  name: "ZMD Mobility",
  version: "1.0.0",
  logo: asset("svg/logo.svg"),
  logoInverse: asset("svg/logo-inverse.svg"),
  signature: asset("svg/signature.svg"),
  symbol: asset("svg/symbol.svg"),
  symbolInverse: asset("svg/symbol-mint.svg"),
  favicon: asset("icons/favicon.svg"),
});
