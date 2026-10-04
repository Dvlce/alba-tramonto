package local.alba;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.Locale;

/** A real Android chart, also exportable as standalone SVG. */
final class NativeBars extends View {
    private final JSONArray samples;
    private final String key,title,unit;
    private final boolean english;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    NativeBars(Context context,JSONArray samples,String key,String title,String unit,boolean english){
        super(context);this.samples=samples;this.key=key;this.title=title;this.unit=unit;this.english=english;
        setContentDescription(title+"; "+samples.toString());
        setMinimumHeight((int)(140*getResources().getDisplayMetrics().density));
    }
    @Override protected void onDraw(Canvas c){
        super.onDraw(c);
        c.save();c.scale(getWidth()/660f,getWidth()/660f);paint.setTextSize(19);paint.setColor(0xffe3eade);c.drawText(title,0,23,paint);
        double max=1;for(int i=0;i<samples.length();i++)max=Math.max(max,samples.optJSONObject(i).optDouble(key,0));
        for(int i=0;i<samples.length();i++){JSONObject s=samples.optJSONObject(i);float y=40+i*60;boolean normal=s.optString("backend").equals("normal");paint.setColor(0xffe3eade);c.drawText(normal?(english?"Normal":"Normale"):(english?"Optimized":"Ottimizzato"),0,y+18,paint);double value=s.optDouble(key,Double.NaN);
            if(Double.isNaN(value)){c.drawText("—",155,y+18,paint);continue;}
            paint.setColor(normal?0xff879985:0xffa1bb94);c.drawRect(155,y,155+(float)(value/max*330),y+25,paint);paint.setColor(0xffe3eade);c.drawText(String.format(Locale.US,"%.2f %s",value,unit),500,y+20,paint);
        }c.restore();
    }
    @Override protected void onMeasure(int width,int height){int w=MeasureSpec.getSize(width);setMeasuredDimension(w,Math.max(getMinimumHeight(),(int)(w*180f/660f)));}
    String svg(){
        double max=1;for(int i=0;i<samples.length();i++)max=Math.max(max,samples.optJSONObject(i).optDouble(key,0));
        StringBuilder out=new StringBuilder("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 660 180\" role=\"img\"><title>"+escape(title)+"</title><text x=\"0\" y=\"24\" font-size=\"18\">"+escape(title)+"</text>");
        for(int i=0;i<samples.length();i++){JSONObject s=samples.optJSONObject(i);int y=40+i*60;boolean normal=s.optString("backend").equals("normal");double value=s.optDouble(key,Double.NaN);out.append("<text x=\"0\" y=\"").append(y+18).append("\" font-size=\"15\">").append(normal?(english?"Normal":"Normale"):(english?"Optimized":"Ottimizzato")).append("</text>");if(Double.isNaN(value))continue;out.append("<rect x=\"155\" y=\"").append(y).append("\" width=\"").append(value/max*330).append("\" height=\"25\" fill=\"").append(normal?"#788275":"#456b43").append("\"/><text x=\"500\" y=\"").append(y+18).append("\" font-size=\"15\">").append(String.format(Locale.US,"%.2f %s",value,unit)).append("</text>");}
        return out.append("</svg>").toString();
    }
    static String escape(String s){return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\"","&quot;").replace("'","&#39;");}
}
