import {dynamicKeyWithoutIndex, isPlannedDynamicStep} from '../gantt/DynamicStepSupport';

export interface GraphQueryItem {
  name: string;
  inputs: {
    dependsOn: {
      solid: {
        name: string;
      };
    }[];
  }[];
  outputs: {
    dependedBy: {
      solid: {
        name: string;
      };
    }[];
  }[];
}

type TraverseStepFunction<T> = (item: T, callback: (nextItem: T) => void) => void;

export class GraphTraverser<T extends GraphQueryItem> {
  itemNameMap: {[name: string]: T} = {};

  constructor(items: T[]) {
    items.forEach((item) => (this.itemNameMap[item.name] = item));
  }

  itemNamed(name: string): T | undefined {
    return this.itemNameMap[name];
  }

  traverse(rootItem: T, nextItemsForItem: TraverseStepFunction<T>, maxDepth: number) {
    const results: {[key: string]: T} = {};
    const queue: [T, number][] = [[rootItem, 0]];

    /** This code performs a breadth-first search, putting all the items discovered at depth 1
     * onto the queue before visiting any items at depth 2. This is important because graphs
     * can look like this:
     *
     *  /---------\
     * A --> B --> C
     */
    while (queue.length) {
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      const [item, depth] = queue.shift()!;
      results[item.name] = item;
      if (depth < maxDepth) {
        nextItemsForItem(item, (next) => {
          if (!(next.name in results)) {
            queue.push([next, depth + 1]);
          }
        });
      }
    }

    return Object.values(results);
  }

  fetchUpstream(item: T, depth: number) {
    const step: TraverseStepFunction<T> = (item, callback) =>
      item.inputs.forEach((input) =>
        input.dependsOn.forEach((d) => {
          const item = this.itemNamed(d.solid.name);
          if (item) {
            callback(item);
          }
        }),
      );

    return this.traverse(item, step, depth);
  }

  fetchDownstream(item: T, depth: number) {
    const step: TraverseStepFunction<T> = (item, callback) =>
      item.outputs.forEach((output) =>
        output.dependedBy.forEach((d) => {
          const item = this.itemNamed(d.solid.name);
          if (item) {
            callback(item);
          }
        }),
      );

    return this.traverse(item, step, depth);
  }
}

function expansionDepthForClause(clause: string) {
  return clause.includes('*') ? Number.MAX_SAFE_INTEGER : clause.length;
}

export function filterByQuery<T extends GraphQueryItem>(items: T[], query: string) {
  if (query === '*' || query === '') {
    return {all: items, focus: []};
  }

  const traverser = new GraphTraverser<T>(items);
  const results = new Set<T>();
  const clauses = query.toLowerCase().split(/(,| AND | and | )/g);
  const focus = new Set<T>();

  for (const clause of clauses) {
    const parts = /(\*?\+*)([.\w\d>\[\?\]\"_\/-]+)(\+*\*?)/.exec(clause.trim());
    if (!parts) {
      continue;
    }
    const [, parentsClause = '', itemName = '', descendentsClause = ''] = parts;

    const itemsMatching = items.filter((s) => {
      const name = s.name.toLowerCase();
      if (isPlannedDynamicStep(itemName.replace(/\"/g, ''))) {
        // When unresolved dynamic step (i.e ends with `[?]`) is selected, match all dynamic steps
        return name.startsWith(dynamicKeyWithoutIndex(itemName.replace(/\"/g, '')));
      } else {
        return /\".*\"/.test(itemName)
          ? name === itemName.replace(/\"/g, '')
          : name.includes(itemName);
      }
    });

    for (const item of itemsMatching) {
      const upDepth = expansionDepthForClause(parentsClause);
      const downDepth = expansionDepthForClause(descendentsClause);

      focus.add(item);
      results.add(item);
      traverser.fetchUpstream(item, upDepth).forEach((other) => results.add(other));
      traverser.fetchDownstream(item, downDepth).forEach((other) => results.add(other));
    }
  }

  return {
    all: Array.from(results),
    focus: Array.from(focus),
  };
}
