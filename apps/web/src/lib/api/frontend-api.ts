import { getPublicApiMode } from "@/config/public-env";
import { mockApi } from "./mock-adapter";
import { realApi } from "./real-adapter";

export const frontendApi = getPublicApiMode() === "real" ? realApi : mockApi;
export const frontendApiMode = getPublicApiMode();
