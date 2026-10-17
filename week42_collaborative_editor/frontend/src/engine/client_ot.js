/**
 * Operational Transformation client-side state machine and algorithms.
 */

export const OpKind = {
  RETAIN: "retain",
  INSERT: "insert",
  DELETE: "delete",
};

export class OpComponent {
  constructor(kind, value) {
    this.kind = kind;
    this.value = value;
  }

  toDict() {
    return { kind: this.kind, value: this.value };
  }

  static fromDict(dict) {
    return new OpComponent(dict.kind, dict.value);
  }
}

export class TextOperation {
  constructor(components = [], baseLength = 0, targetLength = 0) {
    this.components = components;
    this.baseLength = baseLength;
    this.targetLength = targetLength;
  }

  retain(count) {
    if (count <= 0) return this;
    const last = this.components[this.components.length - 1];
    if (last && last.kind === OpKind.RETAIN) {
      last.value += count;
    } else {
      this.components.push(new OpComponent(OpKind.RETAIN, count));
    }
    this.baseLength += count;
    this.targetLength += count;
    return this;
  }

  insert(text) {
    if (!text) return this;
    const last = this.components[this.components.length - 1];
    if (last && last.kind === OpKind.INSERT) {
      last.value += text;
    } else {
      this.components.push(new OpComponent(OpKind.INSERT, text));
    }
    this.targetLength += text.length;
    return this;
  }

  delete(countOrText) {
    const count = typeof countOrText === "string" ? countOrText.length : countOrText;
    if (count <= 0) return this;
    const last = this.components[this.components.length - 1];
    if (last && last.kind === OpKind.DELETE) {
      last.value += count;
    } else {
      this.components.push(new OpComponent(OpKind.DELETE, count));
    }
    this.baseLength += count;
    return this;
  }

  isNoop() {
    return this.components.every((c) => c.kind === OpKind.RETAIN);
  }

  copy() {
    return new TextOperation(
      this.components.map((c) => new OpComponent(c.kind, c.value)),
      this.baseLength,
      this.targetLength
    );
  }

  apply(documentText) {
    if (documentText.length !== this.baseLength) {
      throw new Error(
        `Operation baseLength (${this.baseLength}) does not match document text length (${documentText.length})`
      );
    }

    const parts = [];
    let cursor = 0;

    for (const comp of this.components) {
      if (comp.kind === OpKind.RETAIN) {
        const count = comp.value;
        parts.push(documentText.slice(cursor, cursor + count));
        cursor += count;
      } else if (comp.kind === OpKind.INSERT) {
        parts.push(comp.value);
      } else if (comp.kind === OpKind.DELETE) {
        cursor += comp.value;
      }
    }

    if (cursor !== documentText.length) {
      throw new Error(`Operation ended at cursor ${cursor}, expected ${documentText.length}`);
    }

    const result = parts.join("");
    if (result.length !== this.targetLength) {
      throw new Error(
        `Result text length (${result.length}) does not match targetLength (${this.targetLength})`
      );
    }
    return result;
  }

  toDict() {
    return {
      components: this.components.map((c) => c.toDict()),
      base_length: this.baseLength,
      target_length: this.targetLength,
    };
  }

  static fromDict(dict) {
    const comps = (dict.components || []).map((c) => OpComponent.fromDict(c));
    return new TextOperation(comps, dict.base_length || 0, dict.target_length || 0);
  }
}

/**
 * Pairwise operational transformation.
 */
export function transform(op1, op2, priority = true) {
  if (op1.baseLength !== op2.baseLength) {
    throw new Error(
      `Cannot transform operations with mismatched baseLength: ${op1.baseLength} != ${op2.baseLength}`
    );
  }

  const op1Prime = new TextOperation();
  const op2Prime = new TextOperation();

  const comps1 = op1.components.map((c) => new OpComponent(c.kind, c.value));
  const comps2 = op2.components.map((c) => new OpComponent(c.kind, c.value));

  let i = 0;
  let j = 0;

  while (i < comps1.length || j < comps2.length) {
    const c1 = i < comps1.length ? comps1[i] : null;
    const c2 = j < comps2.length ? comps2[j] : null;

    if (c1 && c2 && c1.kind === OpKind.INSERT && c2.kind === OpKind.INSERT) {
      if (priority) {
        const text1 = String(c1.value);
        op1Prime.insert(text1);
        op2Prime.retain(text1.length);
        i++;
      } else {
        const text2 = String(c2.value);
        op1Prime.retain(text2.length);
        op2Prime.insert(text2);
        j++;
      }
      continue;
    }

    if (c1 && c1.kind === OpKind.INSERT) {
      const text1 = String(c1.value);
      op1Prime.insert(text1);
      op2Prime.retain(text1.length);
      i++;
      continue;
    }

    if (c2 && c2.kind === OpKind.INSERT) {
      const text2 = String(c2.value);
      op1Prime.retain(text2.length);
      op2Prime.insert(text2);
      j++;
      continue;
    }

    if (!c1 || !c2) {
      throw new Error("Cannot transform operations: mismatched component lengths");
    }

    const len1 = Number(c1.value);
    const len2 = Number(c2.value);
    const minLen = Math.min(len1, len2);

    if (c1.kind === OpKind.RETAIN && c2.kind === OpKind.RETAIN) {
      op1Prime.retain(minLen);
      op2Prime.retain(minLen);
    } else if (c1.kind === OpKind.RETAIN && c2.kind === OpKind.DELETE) {
      op2Prime.delete(minLen);
    } else if (c1.kind === OpKind.DELETE && c2.kind === OpKind.RETAIN) {
      op1Prime.delete(minLen);
    } else if (c1.kind === OpKind.DELETE && c2.kind === OpKind.DELETE) {
      // Both deleted same span
    }

    if (len1 > minLen) {
      c1.value = len1 - minLen;
    } else {
      i++;
    }

    if (len2 > minLen) {
      c2.value = len2 - minLen;
    } else {
      j++;
    }
  }

  return [op1Prime, op2Prime];
}

/**
 * Sequential operation composition.
 */
export function compose(op1, op2) {
  if (op1.targetLength !== op2.baseLength) {
    throw new Error(
      `Cannot compose operations: op1.targetLength (${op1.targetLength}) != op2.baseLength (${op2.baseLength})`
    );
  }

  const opComposed = new TextOperation();
  const comps1 = op1.components.map((c) => new OpComponent(c.kind, c.value));
  const comps2 = op2.components.map((c) => new OpComponent(c.kind, c.value));

  let i = 0;
  let j = 0;

  while (i < comps1.length || j < comps2.length) {
    const c1 = i < comps1.length ? comps1[i] : null;
    const c2 = j < comps2.length ? comps2[j] : null;

    if (c1 && c1.kind === OpKind.DELETE) {
      opComposed.delete(Number(c1.value));
      i++;
      continue;
    }

    if (c2 && c2.kind === OpKind.INSERT) {
      opComposed.insert(String(c2.value));
      j++;
      continue;
    }

    if (!c1 || !c2) {
      throw new Error("Cannot compose operations: mismatched intermediate lengths");
    }

    const len1 = c1.kind === OpKind.INSERT ? String(c1.value).length : Number(c1.value);
    const len2 = Number(c2.value);
    const minLen = Math.min(len1, len2);

    if (c1.kind === OpKind.RETAIN && c2.kind === OpKind.RETAIN) {
      opComposed.retain(minLen);
    } else if (c1.kind === OpKind.INSERT && c2.kind === OpKind.RETAIN) {
      opComposed.insert(String(c1.value).slice(0, minLen));
    } else if (c1.kind === OpKind.INSERT && c2.kind === OpKind.DELETE) {
      // Cancelled out
    } else if (c1.kind === OpKind.RETAIN && c2.kind === OpKind.DELETE) {
      opComposed.delete(minLen);
    }

    if (c1.kind === OpKind.INSERT) {
      if (len1 > minLen) {
        c1.value = String(c1.value).slice(minLen);
      } else {
        i++;
      }
    } else {
      if (len1 > minLen) {
        c1.value = len1 - minLen;
      } else {
        i++;
      }
    }

    if (len2 > minLen) {
      c2.value = len2 - minLen;
    } else {
      j++;
    }
  }

  return opComposed;
}

/**
 * Compute TextOperation delta between oldText and newText.
 */
export function createOperationFromDiff(oldText, newText) {
  if (oldText === newText) {
    return new TextOperation().retain(oldText.length);
  }

  let prefixLen = 0;
  while (
    prefixLen < oldText.length &&
    prefixLen < newText.length &&
    oldText[prefixLen] === newText[prefixLen]
  ) {
    prefixLen++;
  }

  let suffixLen = 0;
  while (
    suffixLen < oldText.length - prefixLen &&
    suffixLen < newText.length - prefixLen &&
    oldText[oldText.length - 1 - suffixLen] === newText[newText.length - 1 - suffixLen]
  ) {
    suffixLen++;
  }

  const deletedLen = oldText.length - prefixLen - suffixLen;
  const insertedText = newText.slice(prefixLen, newText.length - suffixLen);

  const op = new TextOperation();
  if (prefixLen > 0) op.retain(prefixLen);
  if (deletedLen > 0) op.delete(deletedLen);
  if (insertedText.length > 0) op.insert(insertedText);
  if (suffixLen > 0) op.retain(suffixLen);

  return op;
}

/**
 * 3-State Operational Transformation Client State Machine.
 */
export class ClientOT {
  constructor(initialRevision = 0) {
    this.state = "SYNCHRONIZED"; // "SYNCHRONIZED" | "AWAITING_ACK" | "AWAITING_ACK_WITH_BUFFER"
    this.revision = initialRevision;
    this.pendingOp = null;
    this.bufferOp = null;
  }

  reset(revision = 0) {
    this.state = "SYNCHRONIZED";
    this.revision = revision;
    this.pendingOp = null;
    this.bufferOp = null;
  }

  applyClient(operation) {
    if (operation.isNoop()) return null;

    if (this.state === "SYNCHRONIZED") {
      this.pendingOp = operation;
      this.state = "AWAITING_ACK";
      return { send: operation, revision: this.revision };
    }

    if (this.state === "AWAITING_ACK") {
      this.bufferOp = operation;
      this.state = "AWAITING_ACK_WITH_BUFFER";
      return null;
    }

    if (this.state === "AWAITING_ACK_WITH_BUFFER") {
      this.bufferOp = compose(this.bufferOp, operation);
      return null;
    }

    return null;
  }

  applyServer(serverOp) {
    if (this.state === "SYNCHRONIZED") {
      this.revision++;
      return { applyToDoc: serverOp };
    }

    if (this.state === "AWAITING_ACK") {
      const [newPending, serverOpPrime] = transform(this.pendingOp, serverOp, true);
      this.pendingOp = newPending;
      this.revision++;
      return { applyToDoc: serverOpPrime };
    }

    if (this.state === "AWAITING_ACK_WITH_BUFFER") {
      const [newPending, opPrime] = transform(this.pendingOp, serverOp, true);
      const [newBuffer, serverOpPrime] = transform(this.bufferOp, opPrime, true);
      this.pendingOp = newPending;
      this.bufferOp = newBuffer;
      this.revision++;
      return { applyToDoc: serverOpPrime };
    }

    return { applyToDoc: serverOp };
  }

  serverAck(newRevision) {
    this.revision = newRevision;

    if (this.state === "AWAITING_ACK") {
      this.pendingOp = null;
      this.state = "SYNCHRONIZED";
      return null;
    }

    if (this.state === "AWAITING_ACK_WITH_BUFFER") {
      const toSend = this.bufferOp;
      this.pendingOp = this.bufferOp;
      this.bufferOp = null;
      this.state = "AWAITING_ACK";
      return { send: toSend, revision: this.revision };
    }

    return null;
  }
}
