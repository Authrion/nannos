/**
 * Budget Guard admin API.
 *
 * Thin throw-on-error wrappers over the generated SDK operations for
 * `/api/v1/admin/budget/*`, kept only for stable call-site names and a small surface that
 * returns `data` directly. They go through the generated bindings (same shared `client`, so
 * the X-Admin-Mode interceptor still applies).
 *
 * Types are RE-EXPORTED from the generated bindings, never hand-maintained here: a
 * hand-written copy drifts from the backend. In particular the USD fields are Decimals,
 * which FastAPI serializes as JSON *strings* — typing them `number` silently breaks
 * currency formatting (`toLocaleString` ignores its options when called on a string).
 */
import {
  getBudgetSettingsApiV1AdminBudgetSettingsGet,
  getBudgetStatusApiV1AdminBudgetStatusGet,
  updateBudgetSettingsApiV1AdminBudgetSettingsPut,
} from './generated/sdk.gen';
import type { BudgetSettings, BudgetSettingsUpdate, BudgetStatus } from './generated/types.gen';

export type { BudgetSettings, BudgetSettingsUpdate, BudgetStatus };

export async function getBudgetSettings(): Promise<BudgetSettings> {
  const { data, error } = await getBudgetSettingsApiV1AdminBudgetSettingsGet();
  if (error) throw error;
  return data as BudgetSettings;
}

export async function updateBudgetSettings(body: BudgetSettingsUpdate): Promise<BudgetSettings> {
  const { data, error } = await updateBudgetSettingsApiV1AdminBudgetSettingsPut({ body });
  if (error) throw error;
  return data as BudgetSettings;
}

export async function getBudgetStatus(): Promise<BudgetStatus> {
  const { data, error } = await getBudgetStatusApiV1AdminBudgetStatusGet();
  if (error) throw error;
  return data as BudgetStatus;
}
