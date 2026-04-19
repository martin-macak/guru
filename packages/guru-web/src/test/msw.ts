import { setupServer } from "msw/node";

export const mockServer = setupServer();

beforeAll(() => mockServer.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => mockServer.resetHandlers());
afterAll(() => mockServer.close());
