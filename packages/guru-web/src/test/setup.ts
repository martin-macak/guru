import "@testing-library/jest-dom/vitest";
import "./msw";

// ReactFlow requires ResizeObserver, which jsdom does not implement.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
