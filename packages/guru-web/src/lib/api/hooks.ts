import { useQuery } from "@tanstack/react-query";

import { getBoot } from "./client";

export function useBootQuery() {
  return useQuery({
    queryKey: ["boot"],
    queryFn: getBoot,
    retry: false,
  });
}
