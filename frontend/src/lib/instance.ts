"use client";

import { createContext, useContext } from "react";

export const InstanceNameContext = createContext("SpecHelper");

export function useInstanceName() {
  return useContext(InstanceNameContext);
}
