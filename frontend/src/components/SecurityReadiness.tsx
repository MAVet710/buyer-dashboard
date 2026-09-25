import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type Readiness = {
  scope: string;
  controls: Array<{ key: string; label: string; status: string; detail: string }>;
};

export function SecurityReadiness() {
  const readiness = useQuery({
    queryKey: ["security-readiness"],
    queryFn: ({ signal }) => apiGet<Readiness>("/api/v1/admin/security-readiness", signal),
  });
  return <details className="streamlit-expander">
    <summary>Security Readiness</summary>
    <div className="streamlit-expander-body">
      {readiness.isLoading ? <p>Checking supported controls...</p> : null}
      {readiness.isError ? <div className="state error">Unable to check security readiness: {readiness.error.message}</div> : null}
      {readiness.data ? <>
        <p>{readiness.data.scope}</p>
        <div className="table-wrap"><table>
          <thead><tr><th>Control</th><th>Status</th><th>Evidence and limits</th></tr></thead>
          <tbody>{readiness.data.controls.map(control => <tr key={control.key}>
            <th scope="row">{control.label}</th><td>{control.status.replaceAll("_", " ")}</td><td>{control.detail}</td>
          </tr>)}</tbody>
        </table></div>
      </> : null}
    </div>
  </details>;
}
