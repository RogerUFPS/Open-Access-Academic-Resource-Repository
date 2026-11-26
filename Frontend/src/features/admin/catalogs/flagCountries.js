const ISO_3166_ALPHA_2_CODES = `
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
DE DJ DK DM DO DZ
EC EE EG EH ER ES ET
FI FJ FK FM FO FR
GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
HK HM HN HR HT HU
ID IE IL IM IN IO IQ IR IS IT
JE JM JO JP
KE KG KH KI KM KN KP KR KW KY KZ
LA LB LC LI LK LR LS LT LU LV LY
MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
NA NC NE NF NG NI NL NO NP NR NU NZ
OM
PA PE PF PG PH PK PL PM PN PR PS PT PW PY
QA
RE RO RS RU RW
SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ
UA UG UM US UY UZ
VA VC VE VG VI VN VU
WF WS
YE YT
ZA ZM ZW
`;

const REGIONAL_INDICATOR_A = 0x1f1e6;
const displayNames = new Intl.DisplayNames(["es"], { type: "region" });

export function countryFlagEmoji(code) {
  if (!/^[A-Z]{2}$/.test(code)) return "";
  return [...code]
    .map((letter) => String.fromCodePoint(REGIONAL_INDICATOR_A + letter.charCodeAt(0) - 65))
    .join("");
}

export const FLAG_COUNTRIES = ISO_3166_ALPHA_2_CODES.trim().split(/\s+/).map((code) => ({
  code,
  name: displayNames.of(code) || code,
  emoji: countryFlagEmoji(code),
})).sort((first, second) => first.name.localeCompare(second.name, "es"));

function normalizeSearch(value) {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("es")
    .trim();
}

export function filterFlagCountries(search) {
  const query = normalizeSearch(search);
  if (!query) return FLAG_COUNTRIES;
  return FLAG_COUNTRIES.filter((country) =>
    normalizeSearch(country.name).includes(query) || country.code.toLocaleLowerCase("es").includes(query)
  );
}

/** @param {string} currentValue @param {string} countryCode */
export function suggestCountryAbbreviation(currentValue, countryCode) {
  return String(currentValue ?? "").trim() ? currentValue : countryCode;
}
