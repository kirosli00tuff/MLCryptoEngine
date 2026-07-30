import CoverageHeatmap from "../components/CoverageHeatmap";
import DataFootprintTile from "../components/DataFootprintTile";
import FeedActivityPanel from "../components/FeedActivityPanel";
import LatencyChart from "../components/LatencyChart";
import LatencyNowTile from "../components/LatencyNowTile";
import LogStream from "../components/LogStream";
import PhaseProgressPanel from "../components/PhaseProgressPanel";
import VenueStatusCard from "../components/VenueStatusCard";

export default function DashboardPage() {
  return (
    <div className="grid grid-cols-12 gap-4 p-5">
      <div className="col-span-3">
        <VenueStatusCard venue="kraken" displayName="Kraken" />
      </div>
      <div className="col-span-3">
        <VenueStatusCard venue="coinbase" displayName="Coinbase" />
      </div>
      <div className="col-span-3">
        <LatencyNowTile />
      </div>
      <div className="col-span-3">
        <DataFootprintTile />
      </div>

      <div className="col-span-8">
        <FeedActivityPanel />
      </div>
      <div className="col-span-4">
        <PhaseProgressPanel />
      </div>

      <div className="col-span-7">
        <LatencyChart />
      </div>
      <div className="col-span-5">
        <CoverageHeatmap />
      </div>

      <div className="col-span-12">
        <LogStream />
      </div>
    </div>
  );
}
