import { useState } from 'react';
import { useSettings } from '../context/SettingsContext';
import { formatMoney } from '../lib/currency';
import { curveGeometry, type CurvePoint } from '../lib/stats';

/**
 * Courbe de bankroll, SVG inline et survolable. Une seule série, en --value,
 * avec une ligne de référence au point de départ.
 */
export function BankrollCurve({ series }: { series: CurvePoint[] }) {
  const { settings } = useSettings();
  const [hover, setHover] = useState<number | null>(null);
  const geo = curveGeometry(series);

  if (series.length < 2) return null;

  const first = series[0];
  const last = series[series.length - 1];
  const up = last.value >= first.value;
  const hovered = hover !== null ? geo.points[hover] : null;
  const slot = (geo.width - 12) / geo.points.length;

  return (
    <div className="vz-curve">
      <div className="vz-curve__head">
        <span>Évolution de la bankroll</span>
        <strong className={up ? 'is-up' : 'is-down'}>
          {up ? '↗ +' : '↘ −'}
          {first.value
            ? Math.abs(((last.value - first.value) / first.value) * 100).toFixed(1)
            : '0.0'}{' '}
          %
        </strong>
      </div>

      <div className="vz-curve__plot">
        {hovered && (
          <div
            className="vz-curve__tip vz-num"
            style={{ left: `${(hovered.x / geo.width) * 100}%` }}
          >
            {formatMoney(hovered.value, settings.currency)} <small>· {hovered.label}</small>
          </div>
        )}
        <svg
          viewBox={`0 0 ${geo.width} ${geo.height}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`Bankroll de ${formatMoney(first.value, settings.currency)} à ${formatMoney(last.value, settings.currency)}`}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <linearGradient id="vzCurveFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="var(--value)" stopOpacity="0.3" />
              <stop offset="1" stopColor="var(--value)" stopOpacity="0" />
            </linearGradient>
          </defs>

          <path d={geo.area} fill="url(#vzCurveFill)" />
          <path
            d={geo.line}
            fill="none"
            stroke={up ? 'var(--value)' : 'var(--danger)'}
            strokeWidth="2.4"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
          <circle
            cx={geo.points[geo.points.length - 1].x}
            cy={geo.points[geo.points.length - 1].y}
            r="3.6"
            fill={up ? 'var(--value)' : 'var(--danger)'}
            stroke="var(--surface)"
            strokeWidth="2"
          />

          {hovered && (
            <>
              <line
                x1={hovered.x}
                x2={hovered.x}
                y1={0}
                y2={geo.height}
                stroke="var(--border)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={hovered.x}
                cy={hovered.y}
                r="4.5"
                fill="var(--value)"
                stroke="var(--surface)"
                strokeWidth="2"
              />
            </>
          )}

          {geo.points.map((p) => (
            <rect
              key={p.index}
              x={p.x - slot / 2}
              y={0}
              width={slot}
              height={geo.height}
              fill="transparent"
              onPointerEnter={() => setHover(p.index)}
              onClick={() => setHover(p.index)}
            />
          ))}
        </svg>
      </div>

      <div className="vz-curve__foot">
        <span>{formatMoney(first.value, settings.currency)}</span>
        <span>{formatMoney(last.value, settings.currency)}</span>
      </div>
    </div>
  );
}
