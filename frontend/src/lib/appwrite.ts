import { Account, Client } from "appwrite";

const endpoint = import.meta.env.VITE_APPWRITE_ENDPOINT || "https://sfo.cloud.appwrite.io/v1";
const projectId = import.meta.env.VITE_APPWRITE_PROJECT_ID || "6a92f61d001bf8be437e";

export function createClient() {
  const client = new Client().setEndpoint(endpoint).setProject(projectId);
  return client;
}

export function getAccount(client?: Client) {
  return new Account(client ?? createClient());
}

export async function signup(email: string, password: string, name: string) {
  const account = getAccount();
  await account.create("unique()", email, password, name);
  return login(email, password);
}

export async function login(email: string, password: string) {
  const account = getAccount();
  await account.createEmailPasswordSession(email, password);
  return account.get();
}

export async function logout() {
  const account = getAccount();
  try { await account.deleteSession("current"); } catch {}
}

export async function getSessionUser() {
  const account = getAccount();
  try { return await account.get(); } catch { return null; }
}

export async function createJwt(): Promise<string | null> {
  const account = getAccount();
  try {
    const jwt = await account.createJWT();
    return jwt.jwt;
  } catch {
    return null;
  }
}
