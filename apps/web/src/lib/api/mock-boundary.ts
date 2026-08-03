/**
 * FE-003 boundary only. No endpoint, field, error code, or business state is
 * declared here before the Review-approved BE-002 OpenAPI contract exists.
 */
export const API_CONTRACT_STATUS = "be-002-pending" as const;
export const API_MOCK_MODE = "contract-required" as const;
export { mockApi, MOCK_ADAPTER_NOTICE } from "./mock-adapter";
export type { FrontendApi } from "./ports";
