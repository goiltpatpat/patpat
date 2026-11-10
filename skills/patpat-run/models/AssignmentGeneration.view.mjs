export const title = "Assignment Generation Fencing Protocol";

export const state = (v) => {
  if (!v.assigned) return "Unassigned (gen 0)";
  const writes = v.writes ? Object.values(v.writes) : [];
  if (writes.length > 0) {
    const last = writes[writes.length - 1];
    if (last.token !== v.generation) {
      return `${v.owner} (gen ${v.generation}) · Stale Write(token ${last.token})`;
    }
    return `${v.owner} (gen ${v.generation}) · Write(token ${last.token})`;
  }
  return `${v.owner} (gen ${v.generation})`;
};

export const step = (action, from, to) => {
  if (!from.assigned && to.assigned) return `Assign to ${to.owner} (token 1)`;
  if (from.assigned && to.assigned && from.generation !== to.generation) {
    return `Reassign to ${to.owner} (token ${to.generation})`;
  }
  if (from.assigned && !to.assigned) return "Revoke lease";
  const fromWrites = from.writes ? Object.values(from.writes) : [];
  const toWrites = to.writes ? Object.values(to.writes) : [];
  if (toWrites.length > fromWrites.length) {
    const last = toWrites[toWrites.length - 1];
    if (last.token !== to.generation) {
      return `accept stale write (token ${last.token} / gen ${to.generation})`;
    }
    return `accept valid write (token ${last.token})`;
  }
  return "reject stale write (fenced out)";
};

export const group = (v) => {
  if (!v.assigned) return "idle";
  const writes = v.writes ? Object.values(v.writes) : [];
  if (writes.length > 0) {
    const last = writes[writes.length - 1];
    if (last.token !== v.generation) return "violation";
    return "committed";
  }
  return "active";
};

export const colors = {
  idle: "teal",
  active: "blue",
  committed: "purple",
  violation: "pink",
};
