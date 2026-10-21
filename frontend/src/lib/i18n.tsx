"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import english from "@/locales/en.json";
import french from "@/locales/fr.json";

export type Language = "en" | "fr";
type Parameters = Record<string, string | number>;
const catalogs: Record<Language, Record<string, string>> = {
  en: english,
  fr: french,
};
const legacy = Object.fromEntries(
  Object.entries(french).map(([key, value]) => [value, key]),
);
const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const patterns = Object.entries(french)
  .filter(([key]) => /\{\w+\}/.test(key))
  .flatMap(([key, value]) =>
    [key, value].map((template) => {
      const names: string[] = [];
      const pieces = template.split(/(\{\w+\})/g).map((piece) => {
        if (/^\{\w+\}$/.test(piece)) {
          names.push(piece.slice(1, -1));
          return "(.+?)";
        }
        return escape(piece);
      });
      return {
        key,
        names,
        expression: new RegExp("^" + pieces.join("") + "$"),
      };
    }),
  );

function interpolate(text: string, parameters: Parameters) {
  return text.replace(/\{(\w+)\}/g, (match, name: string) =>
    String(parameters[name] ?? match),
  );
}

export function translate(
  text: string,
  language: Language,
  parameters: Parameters = {},
): string {
  let key = legacy[text] || text;
  let values = parameters;
  if (!catalogs[language][key]) {
    for (const pattern of patterns) {
      const match = pattern.expression.exec(text);
      if (!match) continue;
      key = pattern.key;
      values = {
        ...Object.fromEntries(
          pattern.names.map((name, index) => [name, match[index + 1]]),
        ),
        ...parameters,
      };
      break;
    }
  }
  return interpolate(catalogs[language][key] || key, values);
}

type TranslationContext = {
  language: Language;
  setLanguage: (language: Language) => void;
  dateLocale: string;
  t: (text: string, parameters?: Parameters) => string;
};
const Context = createContext<TranslationContext | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState<Language>("fr");
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);
  const value = useMemo(
    () => ({
      language,
      setLanguage,
      dateLocale: language === "fr" ? "fr-FR" : "en-US",
      t: (text: string, parameters?: Parameters) =>
        translate(text, language, parameters),
    }),
    [language],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useI18n() {
  const context = useContext(Context);
  if (!context) throw new Error("Translations require I18nProvider");
  return context;
}
