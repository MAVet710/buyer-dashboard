from doobie_panels import run_buyer_doobie
import views.buyer_perfect_view_v2 as v2
v2.run_buyer_doobie = run_buyer_doobie
render_buyer_perfect_view_v3 = v2.render_buyer_perfect_view_v2
