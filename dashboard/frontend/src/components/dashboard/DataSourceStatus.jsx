import { Link } from "@tanstack/react-router";
import { AlertTriangle, Database, Loader2 } from "lucide-react";
import { useEffect, useCallback, useState } from "react";
import { api } from "@/lib/api";

const POLL_RUNNING_MS = 3_000;
const POLL_IDLE_MS = 30_000;

export function DataSourceStatus() {
  return null;
}
