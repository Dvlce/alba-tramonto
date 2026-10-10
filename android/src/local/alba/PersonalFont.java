package local.alba;

import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.text.Editable;
import android.text.Spanned;
import android.text.style.ReplacementSpan;
import android.widget.EditText;
import org.json.*;

/** Render the same saved vector glyphs used by the browser, with native text editing. */
final class PersonalFont {
    static void apply(EditText editor,JSONObject content){
        editor.setTextSize((float)content.optDouble("font_size",16));
        editor.setLetterSpacing((float)(content.optDouble("letter_spacing",0)/Math.max(8,content.optDouble("font_size",16))));
        refresh(editor,content,0,editor.length());
    }
    static void refresh(EditText editor,JSONObject content,int from,int length){
        Editable text=editor.getText();int limit=Math.min(text.length(),from+length);
        from=Math.max(0,Math.min(from,text.length()));
        if(from>0&&from<text.length()&&Character.isLowSurrogate(text.charAt(from)))from--;
        if(limit<text.length()&&Character.isLowSurrogate(text.charAt(limit)))limit++;
        for(Glyph span:text.getSpans(from,limit,Glyph.class))text.removeSpan(span);
        if(!content.optString("font").equals("custom"))return;
        JSONObject font=content.optJSONObject("custom_font"),glyphs=font==null?null:font.optJSONObject("glyphs");
        if(glyphs==null)return;
        for(int start=from;start<limit;){int cp=Character.codePointAt(text,start),end=start+Character.charCount(cp);JSONArray strokes=glyphs.optJSONArray(new String(Character.toChars(cp)));
            if(strokes!=null&&strokes.length()>0)text.setSpan(new Glyph(strokes,(float)font.optDouble("weight",10)),start,end,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            start=end;
        }
    }
    static final class Glyph extends ReplacementSpan {
        final JSONArray strokes;final float weight,left,right;
        Glyph(JSONArray strokes,float weight){this.strokes=strokes;this.weight=weight;float min=300,max=0;for(int i=0;i<strokes.length();i++){JSONArray line=strokes.optJSONArray(i);if(line==null)continue;for(int j=0;j<line.length();j++){JSONArray p=line.optJSONArray(j);if(p!=null){min=Math.min(min,(float)p.optDouble(0));max=Math.max(max,(float)p.optDouble(0));}}}left=min-weight/2;right=max+weight/2;}
        @Override public int getSize(Paint paint,CharSequence text,int start,int end,Paint.FontMetricsInt fm){float size=paint.getTextSize();if(fm!=null){fm.ascent=-(int)Math.ceil(size*.96);fm.descent=(int)Math.ceil(size*.24);fm.top=Math.min(fm.top,fm.ascent);fm.bottom=Math.max(fm.bottom,fm.descent);}return (int)Math.ceil(Math.max(20,right-left+8)*.004f*size);}
        @Override public void draw(Canvas canvas,CharSequence text,int start,int end,float x,int top,int baseline,int bottom,Paint paint){
            Paint ink=new Paint(paint);ink.setStyle(Paint.Style.STROKE);ink.setStrokeWidth(weight);ink.setStrokeCap(Paint.Cap.ROUND);ink.setStrokeJoin(Paint.Join.ROUND);float scale=paint.getTextSize()*.004f;
            canvas.save();canvas.translate(x,baseline);canvas.scale(scale,scale);
            for(int i=0;i<strokes.length();i++){JSONArray line=strokes.optJSONArray(i);if(line==null||line.length()==0)continue;Path path=new Path();for(int j=0;j<line.length();j++){JSONArray p=line.optJSONArray(j);float px=(float)p.optDouble(0)-left+4,py=(float)p.optDouble(1)-240;if(j==0)path.moveTo(px,py);else path.lineTo(px,py);if(line.length()==1){ink.setStyle(Paint.Style.FILL);canvas.drawCircle(px,py,weight/2,ink);ink.setStyle(Paint.Style.STROKE);}}canvas.drawPath(path,ink);}
            canvas.restore();
        }
    }
}
